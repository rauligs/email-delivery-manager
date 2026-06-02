import boto3
import pytest
from botocore.stub import Stubber

from notifications.ses import SesEmailSender


@pytest.fixture
def stubbed_sender() -> tuple[SesEmailSender, Stubber]:
    client = boto3.client("ses", region_name="eu-central-1")
    stubber = Stubber(client)
    return SesEmailSender(client), stubber


def test_send_email_builds_the_expected_ses_request(
    stubbed_sender: tuple[SesEmailSender, Stubber],
) -> None:
    sender, stubber = stubbed_sender
    expected_params = {
        "Source": "noreply@acme.example",
        "Destination": {"ToAddresses": ["ada@example.com"]},
        "Message": {
            "Subject": {"Data": "Welcome", "Charset": "UTF-8"},
            "Body": {"Html": {"Data": "<h1>Welcome, Ada!</h1>", "Charset": "UTF-8"}},
        },
        "ConfigurationSetName": "acme-staging",
    }
    stubber.add_response("send_email", {"MessageId": "msg-123"}, expected_params)

    with stubber:
        response = sender.send_email(
            source="noreply@acme.example",
            to_address="ada@example.com",
            subject="Welcome",
            html_body="<h1>Welcome, Ada!</h1>",
            configuration_set_name="acme-staging",
        )

    assert response["MessageId"] == "msg-123"
    stubber.assert_no_pending_responses()
