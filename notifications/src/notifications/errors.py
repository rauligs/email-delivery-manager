"""Classify a send failure as transient (retriable) or permanent (poison).

At-least-once delivery is only safe if we retry the *right* failures: a throttled
or temporarily unavailable SES, or a network blip, should be retried; a malformed
request or a rejected message should not. This module is the single place that
decides which botocore failure is transient, so the handler can branch on the
answer and the queue's redrive policy never burns retries on poison records.
"""

from botocore.exceptions import ClientError, ReadTimeoutError
from botocore.exceptions import ConnectionError as BotoConnectionError

# SES/SQS error codes that signal a temporary condition worth retrying. Throttling
# and service-unavailable responses are the common transient cases; the rest cover
# AWS's documented retryable codes.
_TRANSIENT_ERROR_CODES = frozenset(
    {
        "Throttling",
        "ThrottlingException",
        "ThrottledException",
        "TooManyRequestsException",
        "RequestThrottled",
        "RequestThrottledException",
        "RequestLimitExceeded",
        "SlowDown",
        "ServiceUnavailable",
        "ServiceUnavailableException",
        "InternalFailure",
        "InternalError",
        "InternalServerError",
        "RequestTimeout",
        "RequestTimeoutException",
    }
)


def is_transient_error(exc: BaseException) -> bool:
    """Return ``True`` if ``exc`` is a transient failure that should be retried.

    Transient: SES throttling, any 5xx server response, and network-level failures
    (connection errors and read timeouts). Everything else — notably 4xx client
    errors such as a rejected message — is treated as permanent (non-retriable).
    """
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        if error.get("Code", "") in _TRANSIENT_ERROR_CODES:
            return True
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return isinstance(status, int) and status >= 500

    # Network-level failures never reached SES, so the request can be safely retried.
    return isinstance(exc, (BotoConnectionError, ReadTimeoutError))
