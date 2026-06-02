"""Offline tests for the operator ``smoke-test`` CLI.

All boto3 and CloudWatch Logs calls are mocked: these tests assert the delivery
message is constructed correctly, that the recipient resolves to the SES
mailbox-simulator (or an explicit override), that correlation/log-polling logic
finds the delivered line and its SES message id, and that exit codes are right.
No real AWS, no network, no tracebacks reach the operator.
"""

import argparse
import json
from typing import Any

import pytest

from notifications import smoke_test


def _args(**overrides: Any) -> argparse.Namespace:
    base: dict[str, Any] = {
        "tenant": "acme",
        "template": "welcome",
        "env": None,
        "region": None,
        "profile": None,
        "mode": "sqs",
        "to": None,
        "simulate": None,
        "from_": None,
        "subject": None,
        "data": "{}",
        "wait": False,
        "timeout": smoke_test.DEFAULT_WAIT_TIMEOUT_SECONDS,
        "poll_interval": smoke_test.DEFAULT_POLL_INTERVAL_SECONDS,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_recipient_defaults_to_success_simulator() -> None:
    assert smoke_test.resolve_recipient(_args()) == "success@simulator.amazonses.com"


def test_simulate_bounce_targets_the_bounce_simulator() -> None:
    expected = "bounce@simulator.amazonses.com"
    assert smoke_test.resolve_recipient(_args(simulate="bounce")) == expected


def test_simulate_complaint_targets_the_complaint_simulator() -> None:
    expected = "complaint@simulator.amazonses.com"
    assert smoke_test.resolve_recipient(_args(simulate="complaint")) == expected


def test_explicit_to_overrides_the_simulator() -> None:
    assert smoke_test.resolve_recipient(_args(to="ada@example.com")) == "ada@example.com"


# --- config resolution -------------------------------------------------------


def test_resolve_config_prefers_flags_over_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "from-env")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_PROFILE", "env-profile")

    config = smoke_test.resolve_config(_args(env="prod", region="eu-west-1", profile="sso"))

    assert config.environment == "prod"
    assert config.region == "eu-west-1"
    assert config.profile == "sso"


def test_resolve_config_requires_an_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(smoke_test.SmokeTestError):
        smoke_test.resolve_config(_args())


# --- message construction ----------------------------------------------------


def _plan(**overrides: Any) -> smoke_test.SmokePlan:
    base: dict[str, Any] = {
        "tenant": "acme",
        "template_name": "welcome",
        "recipient": "success@simulator.amazonses.com",
        "from_address": "noreply@acme.example",
        "subject": "smoke-test corr",
        "correlation_id": "corr",
        "mode": "sqs",
        "wait": False,
        "timeout": 30.0,
        "interval": 1.0,
        "template_data": {"name": "Ada", "product": "Acme"},
    }
    base.update(overrides)
    return smoke_test.SmokePlan(**base)


def test_build_delivery_request_sends_from_a_real_tenant_identity() -> None:
    request = smoke_test.build_delivery_request(_plan())

    assert request.tenant == "acme"
    assert request.template_name == "welcome"
    assert request.to == "success@simulator.amazonses.com"
    assert request.from_address == "noreply@acme.example"
    assert request.subject == "smoke-test corr"
    assert request.template_data == {"name": "Ada", "product": "Acme"}


def test_build_delivery_request_rejects_a_malformed_recipient() -> None:
    with pytest.raises(smoke_test.SmokeTestError):
        smoke_test.build_delivery_request(_plan(recipient="not-an-email"))


# --- log fields extraction ---------------------------------------------------


def test_extract_log_fields_parses_a_plain_json_line() -> None:
    line = json.dumps({"sqs_message_id": "m-1", "outcome": "delivered"})

    assert smoke_test.extract_log_fields(line) == {
        "sqs_message_id": "m-1",
        "outcome": "delivered",
    }


def test_extract_log_fields_parses_an_embedded_json_object() -> None:
    line = '2026-06-02T00:00:00Z INFO {"sqs_message_id": "m-2", "outcome": "delivered"}'

    fields = smoke_test.extract_log_fields(line)

    assert fields is not None
    assert fields["sqs_message_id"] == "m-2"


def test_extract_log_fields_returns_none_for_non_json() -> None:
    assert smoke_test.extract_log_fields("START RequestId: 1234") is None


# --- log polling -------------------------------------------------------------


class _FakeLogs:
    """A fake CloudWatch Logs client returning canned ``filter_log_events`` pages."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    def filter_log_events(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._pages:
            return self._pages.pop(0)
        return {"events": []}


def _event(**fields: Any) -> dict[str, str]:
    return {"message": json.dumps(fields)}


def test_poll_logs_returns_ses_message_id_on_a_delivered_line() -> None:
    logs = _FakeLogs(
        [{"events": [_event(sqs_message_id="corr-1", outcome="delivered", ses_message_id="ses-9")]}]
    )

    result = smoke_test.poll_logs(
        logs,
        "/aws/lambda/notification-engine-delivery-staging",
        "corr-1",
        timeout=30.0,
        interval=1.0,
        sleeper=lambda _s: None,
        clock=iter([0.0, 1.0]).__next__,
    )

    assert result == "ses-9"
    assert logs.calls[0]["logGroupName"] == "/aws/lambda/notification-engine-delivery-staging"


def test_poll_logs_ignores_lines_for_other_correlation_ids() -> None:
    logs = _FakeLogs(
        [
            {"events": [_event(sqs_message_id="other", outcome="delivered", ses_message_id="x")]},
            {"events": [_event(sqs_message_id="corr-2", outcome="delivered", ses_message_id="y")]},
        ]
    )

    result = smoke_test.poll_logs(
        logs,
        "/aws/lambda/g",
        "corr-2",
        timeout=30.0,
        interval=1.0,
        sleeper=lambda _s: None,
        clock=iter([0.0, 1.0, 2.0, 3.0]).__next__,
    )

    assert result == "y"


def test_poll_logs_returns_none_when_the_record_was_rejected() -> None:
    logs = _FakeLogs(
        [{"events": [_event(sqs_message_id="corr-3", outcome="rejected", error_class="X")]}]
    )

    result = smoke_test.poll_logs(
        logs,
        "/aws/lambda/g",
        "corr-3",
        timeout=30.0,
        interval=1.0,
        sleeper=lambda _s: None,
        clock=iter([0.0, 1.0]).__next__,
    )

    assert result is None


def test_poll_logs_times_out_to_none() -> None:
    logs = _FakeLogs([])  # never any matching events
    sleeps: list[float] = []

    result = smoke_test.poll_logs(
        logs,
        "/aws/lambda/g",
        "corr-4",
        timeout=10.0,
        interval=2.0,
        sleeper=sleeps.append,
        clock=iter([0.0, 4.0, 8.0, 12.0]).__next__,
    )

    assert result is None
    assert sleeps  # it slept between attempts before giving up


# --- orchestration: modes ----------------------------------------------------


class _FakeSqs:
    def __init__(self, message_id: str = "sqs-msg-1") -> None:
        self.message_id = message_id
        self.sent: list[dict[str, Any]] = []

    def send_message(self, **kwargs: Any) -> dict[str, str]:
        self.sent.append(kwargs)
        return {"MessageId": self.message_id}


class _FakeLambda:
    def __init__(self) -> None:
        self.invoked: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        self.invoked.append(kwargs)
        return {"StatusCode": 200}


class _FakeSes:
    def __init__(self, message_id: str = "ses-direct-1") -> None:
        self.message_id = message_id
        self.sent: list[dict[str, Any]] = []

    def send_email(self, **kwargs: Any) -> dict[str, str]:
        self.sent.append(kwargs)
        return {"MessageId": self.message_id}


class _FakeCloudFormation:
    def __init__(self, queue_url: str) -> None:
        self._queue_url = queue_url

    def describe_stacks(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "Stacks": [
                {"Outputs": [{"OutputKey": "DeliveryQueueUrl", "OutputValue": self._queue_url}]}
            ]
        }


class _FakeSession:
    """A fake boto3 session vending the appropriate fake client per service."""

    def __init__(self, **clients: Any) -> None:
        self._clients = clients

    def client(self, service_name: str, **_kwargs: Any) -> Any:
        return self._clients[service_name]


def _config() -> smoke_test.SmokeConfig:
    return smoke_test.SmokeConfig(environment="staging", region="eu-central-1", profile=None)


def test_run_smoke_sqs_enqueues_the_request_to_the_stack_queue_url() -> None:
    sqs = _FakeSqs(message_id="sqs-42")
    cfn = _FakeCloudFormation("https://sqs.eu-central-1/queue")
    session = _FakeSession(sqs=sqs, cloudformation=cfn)

    result = smoke_test.run_smoke(_config(), _plan(), session_factory=lambda **_kw: session)

    assert sqs.sent[0]["QueueUrl"] == "https://sqs.eu-central-1/queue"
    body = json.loads(sqs.sent[0]["MessageBody"])
    assert body["tenant"] == "acme"
    assert body["to"] == "success@simulator.amazonses.com"
    assert body["from_address"] == "noreply@acme.example"
    assert result.message_ref == "sqs-42"


def test_run_smoke_sqs_with_wait_polls_logs_for_the_sqs_message_id() -> None:
    sqs = _FakeSqs(message_id="sqs-99")
    cfn = _FakeCloudFormation("https://sqs/q")
    logs = _FakeLogs(
        [{"events": [_event(sqs_message_id="sqs-99", outcome="delivered", ses_message_id="ses-7")]}]
    )
    session = _FakeSession(sqs=sqs, cloudformation=cfn, logs=logs)

    result = smoke_test.run_smoke(
        _config(),
        _plan(wait=True),
        session_factory=lambda **_kw: session,
        sleeper=lambda _s: None,
        clock=iter([0.0, 1.0]).__next__,
    )

    assert result.delivered is True
    assert result.ses_message_id == "ses-7"


def test_run_smoke_lambda_invokes_with_the_correlation_id_as_message_id() -> None:
    fake_lambda = _FakeLambda()
    session = _FakeSession(**{"lambda": fake_lambda})

    result = smoke_test.run_smoke(
        _config(),
        _plan(mode="lambda", correlation_id="corr-lambda"),
        session_factory=lambda **_kw: session,
    )

    payload = json.loads(fake_lambda.invoked[0]["Payload"])
    assert fake_lambda.invoked[0]["FunctionName"] == "notification-engine-delivery-staging"
    assert payload["Records"][0]["messageId"] == "corr-lambda"
    body = json.loads(payload["Records"][0]["body"])
    assert body["template_name"] == "welcome"
    assert result.message_ref == "corr-lambda"


def test_run_smoke_ses_sends_directly_with_the_tenant_configuration_set() -> None:
    ses = _FakeSes(message_id="ses-direct-9")
    session = _FakeSession(ses=ses)

    result = smoke_test.run_smoke(
        _config(), _plan(mode="ses"), session_factory=lambda **_kw: session
    )

    sent = ses.sent[0]
    assert sent["Source"] == "noreply@acme.example"
    assert sent["Destination"]["ToAddresses"] == ["success@simulator.amazonses.com"]
    assert sent["ConfigurationSetName"] == "acme-staging"
    assert "Welcome, Ada!" in sent["Message"]["Body"]["Html"]["Data"]
    assert result.ses_message_id == "ses-direct-9"


def test_run_smoke_ses_with_wait_reports_delivered_without_polling_logs() -> None:
    ses = _FakeSes(message_id="ses-direct-10")
    session = _FakeSession(ses=ses)

    result = smoke_test.run_smoke(
        _config(), _plan(mode="ses", wait=True), session_factory=lambda **_kw: session
    )

    assert result.delivered is True
    assert result.ses_message_id == "ses-direct-10"


# --- CLI entrypoint / exit codes ---------------------------------------------


def _result(**overrides: Any) -> smoke_test.SmokeResult:
    base: dict[str, Any] = {
        "mode": "sqs",
        "recipient": "success@simulator.amazonses.com",
        "correlation_id": "corr",
        "message_ref": "sqs-1",
        "delivered": None,
        "ses_message_id": None,
        "waited": False,
    }
    base.update(overrides)
    return smoke_test.SmokeResult(**base)


def test_main_returns_zero_on_a_successful_enqueue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setattr(smoke_test, "run_smoke", lambda *a, **k: _result())

    exit_code = smoke_test.main(["acme", "welcome"])

    assert exit_code == 0
    assert "sqs-1" in capsys.readouterr().out


def test_main_returns_one_when_wait_times_out_without_delivery(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setattr(
        smoke_test, "run_smoke", lambda *a, **k: _result(delivered=False, waited=True)
    )

    exit_code = smoke_test.main(["acme", "welcome", "--wait"])

    assert exit_code == 1
    assert "Traceback" not in capsys.readouterr().err


def test_main_reports_a_missing_environment_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    exit_code = smoke_test.main(["acme", "welcome"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err


def test_main_rejects_an_unknown_tenant_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")

    exit_code = smoke_test.main(["ghost", "welcome"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err


def test_main_rejects_invalid_template_data_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")

    exit_code = smoke_test.main(["acme", "welcome", "--data", "{not json"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err


def test_to_and_simulate_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        smoke_test.parse_args(["acme", "welcome", "--to", "a@b.com", "--simulate", "bounce"])
