"""A small adapter over the SES send-email call.

Keeping the provider behind this adapter lets the handler express intent
("send this HTML to this recipient as this sender") while tests assert the exact
SES request without touching AWS or the network. The adapter is constructed with
an explicit boto3 SES client so it can be stubbed (botocore ``Stubber``) in tests.
"""

from typing import Any

from .config import Settings, get_settings


class SesEmailSender:
    """Sends rendered emails through an injected boto3 SES client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def send_email(
        self,
        *,
        source: str,
        to_address: str,
        subject: str,
        html_body: str,
        configuration_set_name: str,
    ) -> dict[str, Any]:
        """Build and issue an SES ``SendEmail`` request, returning its response.

        The request is bound to the tenant's derived configuration set so SES
        applies that tenant's event publishing and reputation tracking.
        """
        return self._client.send_email(
            Source=source,
            Destination={"ToAddresses": [to_address]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
            },
            ConfigurationSetName=configuration_set_name,
        )


def build_default_sender(settings: Settings | None = None) -> SesEmailSender:
    """Construct an ``SesEmailSender`` backed by a real region-bound SES client."""
    import boto3

    settings = settings or get_settings()
    client = boto3.client("ses", region_name=settings.aws_region)
    return SesEmailSender(client)
