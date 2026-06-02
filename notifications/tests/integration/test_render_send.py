"""Walking-skeleton integration: SQS event -> render -> SES send, no AWS.

Exercises the handler's render-and-send path end to end with a recording fake
sender so the test can assert both the rendered HTML (including loop output) and
the exact arguments handed to the SES adapter.
"""

import json
from typing import Any

from notifications.handler import process_event


class RecordingSender:
    """Stand-in for ``SesEmailSender`` that records each send call's arguments."""

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


def _sqs_event(*bodies: dict[str, Any]) -> dict[str, Any]:
    return {"Records": [{"body": json.dumps(body)} for body in bodies]}


def test_processes_each_record_and_sends_rendered_html() -> None:
    sender = RecordingSender()
    event = _sqs_event(
        {
            "tenant": "acme",
            "template_name": "welcome",
            "to": "ada@example.com",
            "subject": "Welcome to Acme",
            "from_address": "noreply@acme.example",
            "template_data": {"name": "Ada", "product": "Acme Mail"},
        },
        {
            "tenant": "acme",
            "template_name": "weekly_report",
            "to": "grace@example.com",
            "subject": "Your weekly report",
            "from_address": "reports@acme.example",
            "template_data": {
                "name": "Grace",
                "rows": [
                    {"label": "Sent", "value": 10},
                    {"label": "Opened", "value": 7},
                ],
            },
        },
    )

    responses = process_event(event, sender, environment="staging")

    assert len(responses) == 2
    assert len(sender.calls) == 2

    welcome_call = sender.calls[0]
    assert welcome_call["source"] == "noreply@acme.example"
    assert welcome_call["to_address"] == "ada@example.com"
    assert welcome_call["subject"] == "Welcome to Acme"
    assert welcome_call["configuration_set_name"] == "acme-staging"
    assert "Welcome, Ada!" in welcome_call["html_body"]

    report_call = sender.calls[1]
    assert report_call["to_address"] == "grace@example.com"
    assert report_call["html_body"].count("<tr>") == 3  # header + two data rows
    assert "Sent" in report_call["html_body"]
    assert "Opened" in report_call["html_body"]
