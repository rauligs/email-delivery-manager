"""The delivery request — one queued ask to render a template and send it.

A delivery request names exactly one tenant and one template, carries the
recipient, subject, and resolved sender identity, and the ``template_data`` used
to render the template. It is parsed from the JSON body of an SQS record at the
boundary so the rest of the engine works with a validated, typed object.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# A deliberately strict, single-address shape: exactly one local part, one "@",
# and a dotted domain, with no whitespace or extra "@" that would smuggle in a
# second recipient. ``email-validator`` is not a dependency, so we validate the
# recipient ourselves rather than reaching for ``EmailStr``.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A template name is interpolated straight into the rendered path
# ``templates/<tenant>/<template_name>.html``, so it must be a single flat
# slug: lowercase alphanumerics in ``_``/``-`` separated segments and nothing
# else. This forbids ``/``, ``.``, ``..``, and whitespace, closing off path
# traversal such as ``../other_tenant/template`` that would otherwise let one
# tenant render another tenant's templates.
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")


class DeliveryRequest(BaseModel):
    """A single render-and-send request lifted from an SQS record body."""

    model_config = ConfigDict(extra="forbid")

    tenant: str = Field(min_length=1)
    template_name: str = Field(min_length=1)
    to: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    from_name: str | None = None
    from_address: str | None = None
    template_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("to")
    @classmethod
    def _to_is_a_single_email_address(cls, value: str) -> str:
        if not _EMAIL_RE.match(value):
            raise ValueError("must be a single valid email address")
        return value

    @field_validator("template_name")
    @classmethod
    def _template_name_is_a_safe_slug(cls, value: str) -> str:
        if not _TEMPLATE_NAME_RE.match(value):
            raise ValueError("must be a flat slug of lowercase letters, digits, '-' and '_'")
        return value


class InvalidDeliveryRequest(Exception):
    """A delivery body that can never become valid — a non-retriable failure.

    Raised at the parse boundary for malformed JSON or schema violations so the
    handler can classify the record as poison and branch on it, rather than
    letting a ``ValidationError`` propagate as a transient (retriable) error.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def parse_delivery_request(body: str) -> DeliveryRequest:
    """Parse an SQS record body into a ``DeliveryRequest``.

    Raises ``InvalidDeliveryRequest`` for non-JSON bodies and schema violations
    alike; both are non-retriable.
    """
    try:
        return DeliveryRequest.model_validate_json(body)
    except ValidationError as exc:
        raise InvalidDeliveryRequest(str(exc)) from exc
