"""The handler parses each record before rendering/sending and branches on the
outcome: a valid request is delivered, a schema-invalid one is rejected as a
non-retriable outcome without ever touching the sender.
"""

import json
from typing import Any

from notifications.handler import Delivered, Rejected, process_event, process_record


class RecordingSender:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_email(
        self,
        *,
        source: str,
        to_address: str,
        subject: str,
        html_body: str,
        configuration_set_name: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "source": source,
                "to_address": to_address,
                "subject": subject,
                "html_body": html_body,
                "configuration_set_name": configuration_set_name,
            }
        )
        return {"MessageId": f"msg-{len(self.calls)}"}


def _record(**payload: Any) -> dict[str, Any]:
    return {"body": json.dumps(payload)}


def _valid_payload() -> dict[str, Any]:
    return {
        "tenant": "acme",
        "template_name": "welcome",
        "to": "ada@example.com",
        "subject": "Welcome",
        "from_address": "noreply@acme.example",
        "template_data": {"name": "Ada", "product": "Acme Mail"},
    }


def test_valid_record_is_delivered() -> None:
    sender = RecordingSender()

    outcome = process_record(_record(**_valid_payload()), sender, environment="staging")

    assert isinstance(outcome, Delivered)
    assert len(sender.calls) == 1
    assert outcome.response == {"MessageId": "msg-1"}


def test_delivery_binds_the_derived_configuration_set_and_resolved_sender() -> None:
    sender = RecordingSender()

    process_record(_record(**_valid_payload()), sender, environment="prod")

    assert sender.calls[0]["configuration_set_name"] == "acme-prod"
    assert sender.calls[0]["source"] == "noreply@acme.example"


def test_missing_from_address_falls_back_to_the_tenant_default() -> None:
    sender = RecordingSender()
    payload = _valid_payload()
    del payload["from_address"]

    outcome = process_record(_record(**payload), sender, environment="staging")

    assert isinstance(outcome, Delivered)
    assert sender.calls[0]["source"] == "noreply@acme.example"


def test_unknown_tenant_is_rejected_without_sending() -> None:
    sender = RecordingSender()
    payload = _valid_payload()
    payload["tenant"] = "ghost"

    outcome = process_record(_record(**payload), sender, environment="staging")

    assert isinstance(outcome, Rejected)
    assert sender.calls == []


def test_from_address_outside_tenant_domains_is_rejected_without_sending() -> None:
    sender = RecordingSender()
    payload = _valid_payload()
    payload["from_address"] = "noreply@evil.example"

    outcome = process_record(_record(**payload), sender, environment="staging")

    assert isinstance(outcome, Rejected)
    assert sender.calls == []


def test_invalid_record_is_rejected_without_sending() -> None:
    sender = RecordingSender()
    payload = _valid_payload()
    del payload["to"]

    outcome = process_record(_record(**payload), sender, environment="staging")

    assert isinstance(outcome, Rejected)
    assert outcome.reason
    assert sender.calls == []


def test_non_json_record_is_rejected_without_sending() -> None:
    sender = RecordingSender()

    outcome = process_record({"body": "}not json{"}, sender, environment="staging")

    assert isinstance(outcome, Rejected)
    assert sender.calls == []


def test_event_mixes_delivered_and_rejected_outcomes() -> None:
    sender = RecordingSender()
    bad = _valid_payload()
    bad["to"] = "nope"
    event = {"Records": [_record(**_valid_payload()), _record(**bad)]}

    outcomes = process_event(event, sender, environment="staging")

    assert [type(o) for o in outcomes] == [Delivered, Rejected]
    assert len(sender.calls) == 1
