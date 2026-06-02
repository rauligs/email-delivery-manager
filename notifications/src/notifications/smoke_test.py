"""Operator ``smoke-test`` CLI — live end-to-end send + deploy verification.

This is an out-of-loop tool: it touches real AWS only when a human runs it. In
the Ralph/``verify.sh`` loop its boto3 and CloudWatch Logs calls are mocked, so
every external effect stays behind an injectable seam (``session_factory``,
``sleeper``, ``clock``) and this module never reads ``os.environ`` directly —
config flows through ``config.Settings``.

It proves a *deployed* Environment actually works by sending one real delivery
through the real path. Three modes give progressively narrower diagnostics:

* ``--mode sqs`` (default) — enqueue a ``DeliveryRequest`` to the deployed queue
  (read from the CloudFormation stack outputs); the deployed Lambda renders and
  sends. This exercises the whole path end to end.
* ``--mode lambda`` — invoke the deployed Lambda directly with a synthetic SQS
  event, bypassing the queue, to isolate the function from its trigger.
* ``--mode ses`` — render locally and call SES ``SendEmail`` directly, bypassing
  the queue and Lambda, to isolate the tenant identity and configuration set.

By default it sends FROM a real Tenant identity TO the SES mailbox simulator's
``success@simulator.amazonses.com``; ``--simulate bounce|complaint`` targets the
matching simulator mailbox and ``--to`` overrides to a real address.

With ``--wait`` it injects a unique correlation id and polls CloudWatch Logs
until it observes the correlated *delivered* line (and its SES message id) or the
timeout elapses — exit ``0`` on observed success, ``1`` on failure or timeout.

AWS auth uses the boto3 default credential chain, so ``aws sso login --profile
<profile>`` is the only operator prerequisite; no static keys are read or stored.
Operators see friendly one-line errors and a non-zero exit, never a traceback.
"""

import argparse
import json
import secrets
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TextIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from notifications import deploy
from notifications.config import Settings
from notifications.delivery import DeliveryRequest
from notifications.rendering import render_template
from notifications.ses import SesEmailSender
from notifications.tenants import (
    SenderNotPermitted,
    UnknownTenant,
    configuration_set_name,
    resolve_sender,
    resolve_tenant,
)

# Resource naming is derived the same way the Troposphere stack derives it, so the
# CLI addresses exactly what was deployed for ``ENVIRONMENT``.
FUNCTION_NAME_PREFIX = "notification-engine-delivery"
LOG_GROUP_PREFIX = "/aws/lambda/notification-engine-delivery"
QUEUE_URL_OUTPUT_KEY = "DeliveryQueueUrl"

# The SES mailbox simulator — deterministic addresses that exercise each outcome
# without ever delivering to a real inbox.
SIMULATOR_DOMAIN = "simulator.amazonses.com"
SIMULATOR_ADDRESSES = {
    "success": f"success@{SIMULATOR_DOMAIN}",
    "bounce": f"bounce@{SIMULATOR_DOMAIN}",
    "complaint": f"complaint@{SIMULATOR_DOMAIN}",
}
DEFAULT_RECIPIENT = SIMULATOR_ADDRESSES["success"]

# ``--wait`` polling bounds. The deadline caps total wall time so a stuck send can
# never block the operator forever.
DEFAULT_WAIT_TIMEOUT_SECONDS = 120.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0

# Bound every single-shot AWS call so a hung endpoint cannot block indefinitely.
_CLIENT_CONFIG = Config(
    connect_timeout=10,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "standard"},
)

SessionFactory = Callable[..., Any]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]
TokenFactory = Callable[[int], str]


class SmokeTestError(Exception):
    """An operator-facing smoke-test failure. ``main`` prints it and exits non-zero."""


@dataclass(frozen=True)
class SmokeConfig:
    """The resolved target: environment, region, and optional AWS profile."""

    environment: str
    region: str
    profile: str | None


@dataclass(frozen=True)
class SmokePlan:
    """A fully resolved, validated description of the one send to perform."""

    tenant: str
    template_name: str
    recipient: str
    from_address: str
    subject: str
    correlation_id: str
    mode: str
    wait: bool
    timeout: float
    interval: float
    template_data: dict[str, Any]


@dataclass(frozen=True)
class SmokeResult:
    """The outcome of a run: what was sent and, when waited on, whether it landed.

    ``delivered`` is ``None`` when the run did not wait (so delivery was not
    observed), ``True`` when a correlated delivered line was seen, and ``False``
    when polling timed out or the record was rejected.
    """

    mode: str
    recipient: str
    correlation_id: str
    message_ref: str
    delivered: bool | None
    ses_message_id: str | None
    waited: bool


# --- argument / config resolution -------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the operator CLI flags.

    Flags override the matching environment variable read by ``config.Settings``:
    ``--env``/``ENVIRONMENT``, ``--region``/``AWS_REGION`` (default
    ``eu-central-1``), and ``--profile``/``AWS_PROFILE``.
    """
    parser = argparse.ArgumentParser(
        prog="smoke-test",
        description=(
            "Send one live delivery through a deployed environment and, with --wait, "
            "confirm it by polling CloudWatch Logs for the correlated success."
        ),
    )
    parser.add_argument("tenant", help="Tenant slug from the registry, e.g. acme.")
    parser.add_argument("template", help="Template name to render, e.g. welcome.")
    parser.add_argument(
        "--env",
        "--environment",
        dest="env",
        default=None,
        help="Deployment target, e.g. staging or prod (overrides ENVIRONMENT).",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region (overrides AWS_REGION; default eu-central-1).",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Named AWS profile for a local SSO session (overrides AWS_PROFILE).",
    )
    parser.add_argument(
        "--mode",
        choices=("sqs", "lambda", "ses"),
        default="sqs",
        help="sqs (default, full path), lambda (skip queue), or ses (skip queue+lambda).",
    )
    recipient = parser.add_mutually_exclusive_group()
    recipient.add_argument(
        "--to",
        default=None,
        help="Override the recipient with a real address (default: SES success simulator).",
    )
    recipient.add_argument(
        "--simulate",
        choices=("bounce", "complaint"),
        default=None,
        help="Target the matching SES mailbox-simulator address instead of success.",
    )
    parser.add_argument(
        "--from",
        dest="from_",
        default=None,
        help="Override the sender address (must belong to the tenant's domains).",
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="Override the email subject (a correlation id is used regardless).",
    )
    parser.add_argument(
        "--data",
        default="{}",
        help="Template data as a JSON object (default: {}).",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll CloudWatch Logs for the correlated success; exit 1 on timeout.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_WAIT_TIMEOUT_SECONDS,
        help="Max seconds to poll for the correlated success (default 120).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds between CloudWatch Logs polls (default 5).",
    )
    return parser.parse_args(argv)


def resolve_config(args: argparse.Namespace) -> SmokeConfig:
    """Resolve the target, letting CLI flags override the environment.

    ``config.Settings`` is the single reader of the environment; a missing
    ``ENVIRONMENT`` is reported as a friendly ``SmokeTestError`` rather than a
    pydantic traceback.
    """
    overrides: dict[str, str] = {}
    if args.env is not None:
        overrides["environment"] = args.env
    try:
        settings = Settings(**overrides)
    except ValidationError as exc:
        raise SmokeTestError(
            "ENVIRONMENT is required: pass --env or set the ENVIRONMENT variable."
        ) from exc

    return SmokeConfig(
        environment=settings.environment,
        region=args.region or settings.aws_region,
        profile=args.profile or settings.aws_profile,
    )


def resolve_recipient(args: argparse.Namespace) -> str:
    """Resolve the recipient: ``--to`` wins, then ``--simulate``, then success."""
    if args.to is not None:
        return args.to
    if args.simulate is not None:
        return SIMULATOR_ADDRESSES[args.simulate]
    return DEFAULT_RECIPIENT


def generate_correlation_id(token_factory: TokenFactory = secrets.token_hex) -> str:
    """Mint a unique, log-greppable correlation id for one smoke run."""
    return f"smoke-{token_factory(8)}"


# --- message construction ----------------------------------------------------


def build_delivery_request(plan: SmokePlan) -> DeliveryRequest:
    """Build and validate the ``DeliveryRequest`` for this run.

    Validation happens here (reusing the engine's own schema) so a malformed
    recipient or payload is caught as a friendly ``SmokeTestError`` before any
    AWS call, rather than surfacing as a pydantic traceback or a silent reject.
    """
    try:
        return DeliveryRequest(
            tenant=plan.tenant,
            template_name=plan.template_name,
            to=plan.recipient,
            subject=plan.subject,
            from_address=plan.from_address,
            template_data=plan.template_data,
        )
    except ValidationError as exc:
        raise SmokeTestError(f"invalid delivery request: {exc}") from exc


# --- log polling -------------------------------------------------------------


def extract_log_fields(message: str) -> dict[str, Any] | None:
    """Best-effort parse of a structured log line into its JSON fields.

    The handler logs one JSON object per record, but CloudWatch may prefix the
    message with a timestamp/level, so this falls back to extracting the embedded
    ``{...}`` object. Returns ``None`` for lines that are not our JSON.
    """
    candidate = message.strip()
    try:
        parsed = json.loads(candidate)
    except (TypeError, ValueError):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except (TypeError, ValueError):
            return None
    return parsed if isinstance(parsed, dict) else None


def _filter_log_pages(logs_client: Any, log_group: str, token: str) -> list[dict[str, Any]]:
    """Read every ``filter_log_events`` page for ``token`` in one polling attempt."""
    events: list[dict[str, Any]] = []
    next_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"logGroupName": log_group, "filterPattern": f'"{token}"'}
        if next_token is not None:
            kwargs["nextToken"] = next_token
        response = logs_client.filter_log_events(**kwargs)
        events.extend(response.get("events", []))
        next_token = response.get("nextToken")
        if not next_token:
            return events


def poll_logs(
    logs_client: Any,
    log_group: str,
    correlation_token: str,
    *,
    timeout: float,
    interval: float,
    sleeper: Sleeper = time.sleep,
    clock: Clock = time.monotonic,
) -> str | None:
    """Poll CloudWatch Logs until the correlated outcome is observed or time runs out.

    Returns the SES message id when a ``delivered`` line for ``correlation_token``
    appears, ``None`` if the correlated line is a non-delivered (rejected/retriable)
    outcome — a terminal failure — or if the deadline elapses first.
    """
    deadline = clock() + timeout
    while True:
        for event in _filter_log_pages(logs_client, log_group, correlation_token):
            fields = extract_log_fields(event.get("message", ""))
            if fields is None or fields.get("sqs_message_id") != correlation_token:
                continue
            if fields.get("outcome") == "delivered":
                return fields.get("ses_message_id")
            # A correlated but non-delivered outcome will never become delivered.
            return None
        if clock() >= deadline:
            return None
        sleeper(interval)


# --- AWS-facing dispatch -----------------------------------------------------


def _client(session: Any, service: str) -> Any:
    """Build a timeout-bounded client for ``service`` from ``session``."""
    return session.client(service, config=_CLIENT_CONFIG)


def queue_url_for(config: SmokeConfig, *, session_factory: SessionFactory) -> str:
    """Read the deployed delivery queue URL from the stack's CloudFormation outputs."""
    stack_name = f"{deploy.STACK_NAME_PREFIX}-{config.environment}"
    try:
        outputs = deploy.stack_outputs(
            stack_name=stack_name,
            region=config.region,
            profile=config.profile,
            session_factory=session_factory,
        )
    except deploy.DeployError as exc:
        raise SmokeTestError(str(exc)) from exc
    queue_url = outputs.get(QUEUE_URL_OUTPUT_KEY)
    if not queue_url:
        raise SmokeTestError(
            f"stack {stack_name!r} has no {QUEUE_URL_OUTPUT_KEY} output; is it deployed?"
        )
    return queue_url


def _dispatch_sqs(
    session: Any, config: SmokeConfig, request: DeliveryRequest, *, session_factory: SessionFactory
) -> str:
    """Enqueue the request to the deployed queue; return the SQS message id."""
    queue_url = queue_url_for(config, session_factory=session_factory)
    sqs = _client(session, "sqs")
    response = sqs.send_message(QueueUrl=queue_url, MessageBody=request.model_dump_json())
    return response["MessageId"]


def _dispatch_lambda(session: Any, config: SmokeConfig, plan: SmokePlan, body: str) -> None:
    """Invoke the deployed Lambda with a synthetic single-record SQS event.

    The record's ``messageId`` is set to our correlation id so the handler logs it
    as ``sqs_message_id`` and ``--wait`` can find the correlated line.
    """
    lambda_client = _client(session, "lambda")
    event = {"Records": [{"messageId": plan.correlation_id, "body": body}]}
    lambda_client.invoke(
        FunctionName=f"{FUNCTION_NAME_PREFIX}-{config.environment}",
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode("utf-8"),
    )


def _dispatch_ses(session: Any, config: SmokeConfig, plan: SmokePlan) -> str:
    """Render locally and send straight through SES; return the SES message id."""
    tenant = resolve_tenant(plan.tenant)
    html_body = render_template(plan.tenant, plan.template_name, plan.template_data)
    sender = SesEmailSender(_client(session, "ses"))
    response = sender.send_email(
        source=plan.from_address,
        to_address=plan.recipient,
        subject=plan.subject,
        html_body=html_body,
        configuration_set_name=configuration_set_name(tenant, config.environment),
    )
    return response["MessageId"]


def run_smoke(
    config: SmokeConfig,
    plan: SmokePlan,
    *,
    session_factory: SessionFactory = boto3.Session,
    sleeper: Sleeper = time.sleep,
    clock: Clock = time.monotonic,
    out: TextIO | None = None,
) -> SmokeResult:
    """Construct, dispatch (per ``mode``), and — when ``--wait`` — confirm one send."""
    out = out if out is not None else sys.stdout
    request = build_delivery_request(plan)
    session = session_factory(profile_name=config.profile, region_name=config.region)

    ses_message_id: str | None = None
    if plan.mode == "sqs":
        message_ref = _dispatch_sqs(session, config, request, session_factory=session_factory)
    elif plan.mode == "lambda":
        _dispatch_lambda(session, config, plan, request.model_dump_json())
        message_ref = plan.correlation_id
    else:  # ses
        ses_message_id = _dispatch_ses(session, config, plan)
        message_ref = ses_message_id

    print(
        f"Dispatched via {plan.mode}: tenant={plan.tenant} template={plan.template_name} "
        f"to={plan.recipient} correlation={plan.correlation_id} ref={message_ref}",
        file=out,
    )

    delivered: bool | None = None
    if plan.wait:
        if plan.mode == "ses":
            # No queue/Lambda log line to correlate against; SES accepting the send
            # (a returned message id) is the observable success here.
            delivered = ses_message_id is not None
        else:
            log_group = f"{LOG_GROUP_PREFIX}-{config.environment}"
            ses_message_id = poll_logs(
                _client(session, "logs"),
                log_group,
                message_ref,
                timeout=plan.timeout,
                interval=plan.interval,
                sleeper=sleeper,
                clock=clock,
            )
            delivered = ses_message_id is not None

    return SmokeResult(
        mode=plan.mode,
        recipient=plan.recipient,
        correlation_id=plan.correlation_id,
        message_ref=message_ref,
        delivered=delivered,
        ses_message_id=ses_message_id,
        waited=plan.wait,
    )


# --- presentation / entrypoint ----------------------------------------------


def _print_result(result: SmokeResult, out: TextIO) -> None:
    """Print a concise human summary of the run."""
    if not result.waited:
        print(
            f"Submitted. Re-run with --wait to confirm delivery of {result.message_ref!r}.",
            file=out,
        )
        return
    if result.delivered:
        print(f"Confirmed delivered. SES message id: {result.ses_message_id}", file=out)
    else:
        print("Not confirmed: no correlated success observed before the timeout.", file=out)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: returns 0 on success, 1 on a handled failure or timeout."""
    args = parse_args(argv)
    try:
        config = resolve_config(args)
        tenant = resolve_tenant(args.tenant)
        from_address = resolve_sender(tenant, args.from_)
        try:
            template_data = json.loads(args.data)
        except ValueError as exc:
            raise SmokeTestError(f"--data is not valid JSON: {exc}") from exc
        if not isinstance(template_data, dict):
            raise SmokeTestError("--data must be a JSON object.")

        correlation_id = generate_correlation_id()
        plan = SmokePlan(
            tenant=tenant.slug,
            template_name=args.template,
            recipient=resolve_recipient(args),
            from_address=from_address,
            subject=args.subject or f"smoke-test {correlation_id}",
            correlation_id=correlation_id,
            mode=args.mode,
            wait=args.wait,
            timeout=args.timeout,
            interval=args.poll_interval,
            template_data=template_data,
        )
        result = run_smoke(config, plan)
    except (SmokeTestError, UnknownTenant, SenderNotPermitted) as exc:
        print(f"smoke-test failed: {exc}", file=sys.stderr)
        return 1
    except (BotoCoreError, ClientError) as exc:  # AWS/credential errors, friendly one-liner
        print(f"smoke-test failed: {exc}", file=sys.stderr)
        return 1

    _print_result(result, sys.stdout)
    if result.waited and not result.delivered:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
