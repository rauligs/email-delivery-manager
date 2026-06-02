"""Batch-level behaviour: a mixed SQS batch must yield the right partial-batch
response, forward poison records to the DLQ, and log one redacted line per record.
"""

import json
import logging
from typing import Any

from botocore.exceptions import ClientError

from notifications.handler import (
    Delivered,
    Rejected,
    Retriable,
    build_log_fields,
    handle_event,
)


class RecordingSender:
    """Sends successfully unless told to raise a specific error for a recipient."""

    def __init__(self, errors: dict[str, Exception] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._errors = errors or {}

    def send_email(self, *, to_address: str, **kwargs: Any) -> dict[str, Any]:
        if to_address in self._errors:
            raise self._errors[to_address]
        self.calls.append({"to_address": to_address, **kwargs})
        return {"MessageId": f"ses-{len(self.calls)}"}


class RecordingForwarder:
    def __init__(self) -> None:
        self.forwarded: list[dict[str, Any]] = []

    def forward(self, record: dict[str, Any]) -> dict[str, Any]:
        self.forwarded.append(record)
        return {"MessageId": f"dlq-{len(self.forwarded)}"}


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "tenant": "acme",
        "template_name": "welcome",
        "to": "ada@example.com",
        "subject": "Welcome",
        "from_address": "noreply@acme.example",
        "template_data": {"name": "Ada", "product": "Acme Mail"},
    }
    payload.update(overrides)
    return payload


def _record(message_id: str, **overrides: Any) -> dict[str, Any]:
    return {"messageId": message_id, "body": json.dumps(_payload(**overrides))}


def _throttle() -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "ThrottlingException", "Message": "slow down"},
            "ResponseMetadata": {"HTTPStatusCode": 429},
        },
        "SendEmail",
    )


def test_mixed_batch_reports_only_transient_failures_and_parks_poison() -> None:
    # ok -> delivered; throttled -> transient (retry); ghost tenant -> poison (DLQ).
    sender = RecordingSender(errors={"throttled@example.com": _throttle()})
    dlq = RecordingForwarder()
    event = {
        "Records": [
            _record("m-ok", to="ada@example.com"),
            _record("m-transient", to="throttled@example.com"),
            _record("m-poison", tenant="ghost"),
        ]
    }

    response = handle_event(event, sender, dlq, environment="staging")

    # Only the transient record is reported back for redelivery.
    assert response == {"batchItemFailures": [{"itemIdentifier": "m-transient"}]}
    # The poison record — and only it — is forwarded to the DLQ.
    assert len(dlq.forwarded) == 1
    assert dlq.forwarded[0]["messageId"] == "m-poison"
    # The successful send happened; the throttled one did not record a call.
    assert [c["to_address"] for c in sender.calls] == ["ada@example.com"]


def test_empty_event_yields_no_failures() -> None:
    response = handle_event(
        {"Records": []}, RecordingSender(), RecordingForwarder(), environment="x"
    )

    assert response == {"batchItemFailures": []}


def test_log_fields_redact_recipient_and_never_include_template_data() -> None:
    record = _record("m-1", to="ada@example.com")
    outcome = Delivered(response={"MessageId": "ses-42"})

    fields = build_log_fields(record, outcome)

    assert fields == {
        "tenant": "acme",
        "template_name": "welcome",
        "sqs_message_id": "m-1",
        "ses_message_id": "ses-42",
        "recipient_domain": "example.com",
        "outcome": "delivered",
        "error_class": None,
    }
    # Defence in depth: the full address and the payload never appear anywhere.
    serialized = json.dumps(fields)
    assert "ada@example.com" not in serialized
    assert "template_data" not in serialized
    assert "Acme Mail" not in serialized


def test_log_fields_carry_the_error_class_for_failures() -> None:
    rejected = build_log_fields(_record("m-2", tenant="ghost"), Rejected("nope", "UnknownTenant"))
    assert rejected["outcome"] == "rejected"
    assert rejected["error_class"] == "UnknownTenant"
    assert rejected["ses_message_id"] is None

    retriable = build_log_fields(_record("m-3"), Retriable("slow", "ThrottlingException"))
    assert retriable["outcome"] == "retriable"
    assert retriable["error_class"] == "ThrottlingException"


def test_handle_event_emits_one_log_line_per_record(caplog: Any) -> None:
    sender = RecordingSender(errors={"throttled@example.com": _throttle()})
    event = {
        "Records": [
            _record("m-ok", to="ada@example.com"),
            _record("m-transient", to="throttled@example.com"),
            _record("m-poison", tenant="ghost"),
        ]
    }

    with caplog.at_level(logging.INFO, logger="notifications.delivery"):
        handle_event(event, sender, RecordingForwarder(), environment="staging")

    lines = [json.loads(r.message) for r in caplog.records if r.name == "notifications.delivery"]
    assert len(lines) == 3
    assert {line["outcome"] for line in lines} == {"delivered", "retriable", "rejected"}
