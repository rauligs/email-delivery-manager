"""The DLQ forwarder parks a record's raw body via sqs:SendMessage."""

import boto3
import pytest
from botocore.stub import Stubber

from notifications.dlq import DlqForwarder


@pytest.fixture
def stubbed_forwarder() -> tuple[DlqForwarder, Stubber]:
    client = boto3.client("sqs", region_name="eu-central-1")
    stubber = Stubber(client)
    return DlqForwarder(client, "https://sqs.example/dlq"), stubber


def test_forward_sends_the_record_body_to_the_dlq(
    stubbed_forwarder: tuple[DlqForwarder, Stubber],
) -> None:
    forwarder, stubber = stubbed_forwarder
    expected_params = {
        "QueueUrl": "https://sqs.example/dlq",
        "MessageBody": '{"tenant": "acme"}',
    }
    stubber.add_response("send_message", {"MessageId": "dlq-1"}, expected_params)

    with stubber:
        response = forwarder.forward({"body": '{"tenant": "acme"}'})

    assert response["MessageId"] == "dlq-1"
    stubber.assert_no_pending_responses()
