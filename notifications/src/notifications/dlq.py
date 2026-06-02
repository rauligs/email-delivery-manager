"""A small adapter that forwards poison records to the dead-letter queue.

When a record hits a non-retriable error we must not let it cycle back onto the
source queue and burn retries. Instead the handler explicitly forwards it to the
DLQ (``sqs:SendMessage``) and then treats it as handled. Keeping the SQS call
behind this adapter lets the handler express intent ("park this record") while
tests assert the exact request without touching AWS or the network.
"""

from typing import Any

from .config import Settings, get_settings


class DlqForwarder:
    """Forwards a record's body to the dead-letter queue via an injected client."""

    def __init__(self, client: Any, queue_url: str) -> None:
        self._client = client
        self._queue_url = queue_url

    def forward(self, record: dict[str, Any]) -> dict[str, Any]:
        """Send the record's original body to the DLQ, returning the SQS response.

        The raw body is forwarded verbatim so the parked message is reprocessable
        and debuggable; no ``template_data`` is inspected or logged here.
        """
        return self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=record["body"],
        )


def build_default_forwarder(settings: Settings | None = None) -> DlqForwarder:
    """Construct a ``DlqForwarder`` backed by a real region-bound SQS client.

    Raises ``RuntimeError`` if the DLQ URL is not configured, since forwarding
    poison records is required for safe at-least-once delivery.
    """
    import boto3

    settings = settings or get_settings()
    if not settings.delivery_dlq_url:
        raise RuntimeError("DELIVERY_DLQ_URL is not configured")
    client = boto3.client("sqs", region_name=settings.aws_region)
    return DlqForwarder(client, settings.delivery_dlq_url)
