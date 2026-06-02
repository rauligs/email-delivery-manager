"""Validation of the SQS delivery-request payload at the engine boundary.

A delivery request is parsed from a raw SQS body. Anything that can never become
valid — a missing required field, a malformed recipient, the wrong type, or a
body that is not even JSON — must surface as a non-retriable failure that the
handler can branch on, rather than as an exception treated as a transient error.
"""

import json

import pytest

from notifications.delivery import (
    DeliveryRequest,
    InvalidDeliveryRequest,
    parse_delivery_request,
)


def _valid_body(**overrides: object) -> str:
    payload: dict[str, object] = {
        "tenant": "acme",
        "template_name": "welcome",
        "to": "ada@example.com",
        "subject": "Welcome to Acme",
        "from_address": "noreply@acme.example",
        "template_data": {"name": "Ada", "product": "Acme Mail"},
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_parses_a_valid_payload() -> None:
    request = parse_delivery_request(_valid_body())

    assert isinstance(request, DeliveryRequest)
    assert request.tenant == "acme"
    assert request.template_name == "welcome"
    assert request.to == "ada@example.com"
    assert request.subject == "Welcome to Acme"
    assert request.from_address == "noreply@acme.example"
    assert request.template_data == {"name": "Ada", "product": "Acme Mail"}


def test_optional_fields_default_when_omitted() -> None:
    body = json.dumps(
        {
            "tenant": "acme",
            "template_name": "welcome",
            "to": "ada@example.com",
            "subject": "Hi",
        }
    )

    request = parse_delivery_request(body)

    assert request.from_name is None
    assert request.from_address is None
    assert request.template_data == {}


def test_from_name_is_accepted_when_supplied() -> None:
    request = parse_delivery_request(_valid_body(from_name="Acme Mail"))

    assert request.from_name == "Acme Mail"


@pytest.mark.parametrize("field", ["tenant", "template_name", "to", "subject"])
def test_missing_required_field_is_non_retriable(field: str) -> None:
    payload = json.loads(_valid_body())
    del payload[field]

    with pytest.raises(InvalidDeliveryRequest):
        parse_delivery_request(json.dumps(payload))


@pytest.mark.parametrize(
    "bad_email",
    ["not-an-email", "ada@", "@example.com", "ada example.com", "a@b@c.com", ""],
)
def test_malformed_recipient_is_non_retriable(bad_email: str) -> None:
    with pytest.raises(InvalidDeliveryRequest):
        parse_delivery_request(_valid_body(to=bad_email))


def test_multiple_recipients_are_rejected() -> None:
    with pytest.raises(InvalidDeliveryRequest):
        parse_delivery_request(_valid_body(to="ada@example.com, grace@example.com"))


@pytest.mark.parametrize(
    "bad_name",
    [
        "../other_tenant/template",
        "../../etc/passwd",
        "sub/dir",
        "welcome.html",
        "name.with.dots",
        "UPPER",
        "has space",
        "_leading",
        "trailing_",
        "weird!",
        "",
    ],
)
def test_template_name_path_traversal_is_non_retriable(bad_name: str) -> None:
    with pytest.raises(InvalidDeliveryRequest):
        parse_delivery_request(_valid_body(template_name=bad_name))


@pytest.mark.parametrize("good_name", ["welcome", "weekly_report", "v2-digest", "abc123"])
def test_safe_template_names_are_accepted(good_name: str) -> None:
    request = parse_delivery_request(_valid_body(template_name=good_name))

    assert request.template_name == good_name


def test_wrong_types_are_non_retriable() -> None:
    with pytest.raises(InvalidDeliveryRequest):
        parse_delivery_request(_valid_body(template_data=["not", "an", "object"]))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(InvalidDeliveryRequest):
        parse_delivery_request(_valid_body(surprise="boom"))


def test_non_json_body_is_non_retriable() -> None:
    with pytest.raises(InvalidDeliveryRequest):
        parse_delivery_request("this is not json {")
