"""Lambda entrypoint: consume an SQS event, render, send, and report outcomes.

``handler`` is the deployed entrypoint and wires the real SES sender and DLQ
forwarder. ``handle_event`` holds the batch-level policy: it classifies each
record, logs one structured line per record, forwards poison records to the DLQ,
and returns an SQS partial-batch response so only transient failures are retried.
``process_record`` holds the per-record logic and takes its collaborators
explicitly so they can be exercised with stubs and no AWS.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from jinja2 import TemplateError

from .config import get_settings
from .delivery import InvalidDeliveryRequest, parse_delivery_request
from .dlq import DlqForwarder, build_default_forwarder
from .errors import is_transient_error
from .rendering import render_template
from .ses import SesEmailSender, build_default_sender
from .tenants import (
    SenderNotPermitted,
    UnknownTenant,
    configuration_set_name,
    resolve_sender,
    resolve_tenant,
)

logger = logging.getLogger("notifications.delivery")


@dataclass(frozen=True)
class Delivered:
    """A record that was rendered and accepted by the sender."""

    response: dict[str, Any]


@dataclass(frozen=True)
class Rejected:
    """A non-retriable outcome (poison): forward to the DLQ, never retry."""

    reason: str
    error_class: str


@dataclass(frozen=True)
class Retriable:
    """A transient failure: report to the source queue so it is retried."""

    reason: str
    error_class: str


DeliveryOutcome = Delivered | Rejected | Retriable


def process_record(
    record: dict[str, Any], sender: SesEmailSender, *, environment: str
) -> DeliveryOutcome:
    """Parse, then render and send a single SQS record's delivery request.

    Returns one of three outcomes so the caller can route each record correctly:

    * ``Rejected`` — a non-retriable error (invalid payload, unknown tenant,
      sender outside the tenant's domains, or a missing/broken template). The body
      can never succeed, so it is parked in the DLQ rather than retried.
    * ``Retriable`` — a transient send failure (SES throttling/5xx, network or
      timeout). The same body may succeed later, so it is reported for retry.
    * ``Delivered`` — the send was accepted by SES.

    The resolved tenant determines the sender identity (anti-spoofing) and the
    derived ``<slug>-<environment>`` SES configuration set the send is bound to.
    """
    try:
        request = parse_delivery_request(record["body"])
    except InvalidDeliveryRequest as exc:
        return Rejected(reason=exc.message, error_class="InvalidDeliveryRequest")

    try:
        tenant = resolve_tenant(request.tenant)
        source = resolve_sender(tenant, request.from_address)
    except (UnknownTenant, SenderNotPermitted) as exc:
        return Rejected(reason=str(exc), error_class=type(exc).__name__)

    try:
        html_body = render_template(request.tenant, request.template_name, request.template_data)
    except TemplateError as exc:
        return Rejected(reason=str(exc), error_class=type(exc).__name__)

    try:
        response = sender.send_email(
            source=source,
            to_address=request.to,
            subject=request.subject,
            html_body=html_body,
            configuration_set_name=configuration_set_name(tenant, environment),
        )
    except Exception as exc:  # noqa: BLE001 — classified, then re-routed not swallowed
        if is_transient_error(exc):
            return Retriable(reason=str(exc), error_class=type(exc).__name__)
        return Rejected(reason=str(exc), error_class=type(exc).__name__)

    return Delivered(response=response)


def process_event(
    event: dict[str, Any], sender: SesEmailSender, *, environment: str
) -> list[DeliveryOutcome]:
    """Process every record in an SQS event with the given sender."""
    return [
        process_record(record, sender, environment=environment)
        for record in event.get("Records", [])
    ]


def _safe_body_fields(body: Any) -> dict[str, Any]:
    """Best-effort parse of an SQS body to dict, for logging only.

    Never raises: a body we could not parse for delivery still needs a log line.
    """
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _recipient_domain(fields: dict[str, Any]) -> str | None:
    """Redact a recipient to its domain so the address is never logged."""
    to = fields.get("to")
    if isinstance(to, str) and "@" in to:
        return to.rpartition("@")[2]
    return None


def build_log_fields(record: dict[str, Any], outcome: DeliveryOutcome) -> dict[str, Any]:
    """Build the structured, redaction-safe log fields for one record's outcome.

    ``template_data`` is never read here; the recipient is reduced to its domain.
    """
    fields = _safe_body_fields(record.get("body"))
    ses_message_id = outcome.response.get("MessageId") if isinstance(outcome, Delivered) else None
    error_class = outcome.error_class if isinstance(outcome, Rejected | Retriable) else None
    outcome_label = {
        Delivered: "delivered",
        Rejected: "rejected",
        Retriable: "retriable",
    }[type(outcome)]

    return {
        "tenant": fields.get("tenant"),
        "template_name": fields.get("template_name"),
        "sqs_message_id": record.get("messageId"),
        "ses_message_id": ses_message_id,
        "recipient_domain": _recipient_domain(fields),
        "outcome": outcome_label,
        "error_class": error_class,
    }


def log_record_outcome(record: dict[str, Any], outcome: DeliveryOutcome) -> dict[str, Any]:
    """Emit one structured JSON log line for a record and return its fields."""
    fields = build_log_fields(record, outcome)
    logger.info(json.dumps(fields))
    return fields


def handle_event(
    event: dict[str, Any],
    sender: SesEmailSender,
    dlq: DlqForwarder,
    *,
    environment: str,
) -> dict[str, list[dict[str, str]]]:
    """Process an SQS event and return an SQS partial-batch response.

    Each record is classified, logged, and routed:

    * ``Retriable`` records go into ``batchItemFailures`` so SQS redelivers them.
    * ``Rejected`` records are forwarded to the DLQ and treated as handled, so
      they leave the source queue without being counted as failures.
    * ``Delivered`` records are simply acknowledged.
    """
    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        outcome = process_record(record, sender, environment=environment)
        log_record_outcome(record, outcome)

        if isinstance(outcome, Retriable):
            batch_item_failures.append({"itemIdentifier": record["messageId"]})
        elif isinstance(outcome, Rejected):
            dlq.forward(record)

    return {"batchItemFailures": batch_item_failures}


def handler(
    event: dict[str, Any], context: object | None = None
) -> dict[str, list[dict[str, str]]]:
    """AWS Lambda entrypoint for SQS-triggered delivery requests."""
    settings = get_settings()
    return handle_event(
        event,
        build_default_sender(settings),
        build_default_forwarder(settings),
        environment=settings.environment,
    )
