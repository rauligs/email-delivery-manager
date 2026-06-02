"""Transient vs. permanent classification decides what gets retried."""

from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from notifications.errors import is_transient_error


def _client_error(code: str, status: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "boom"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "SendEmail",
    )


def test_throttling_is_transient() -> None:
    assert is_transient_error(_client_error("ThrottlingException", 429)) is True


def test_server_error_is_transient() -> None:
    assert is_transient_error(_client_error("ServiceUnavailable", 503)) is True


def test_any_5xx_status_is_transient() -> None:
    assert is_transient_error(_client_error("SomethingElse", 500)) is True


def test_network_failures_are_transient() -> None:
    assert is_transient_error(EndpointConnectionError(endpoint_url="https://ses")) is True
    assert is_transient_error(ReadTimeoutError(endpoint_url="https://ses")) is True


def test_client_4xx_is_not_transient() -> None:
    assert is_transient_error(_client_error("MessageRejected", 400)) is False


def test_unrelated_exception_is_not_transient() -> None:
    assert is_transient_error(ValueError("nope")) is False
