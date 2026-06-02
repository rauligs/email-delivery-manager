"""Offline tests for the operator ``tenant-setup`` CLI.

All boto3 calls are mocked with botocore ``Stubber``: these tests assert the
emitted Cloudflare-ready DNS records, idempotent identity provisioning, DKIM
status polling, and SES sandbox reporting. No real AWS, no network, and no
traceback ever reaches the operator.
"""

import io

import boto3
import pytest
from botocore.stub import Stubber

from notifications import tenant_setup as ts
from notifications.tags import standard_tags
from notifications.tenants import resolve_tenant


@pytest.fixture
def sesv2() -> tuple[object, Stubber]:
    client = boto3.client("sesv2", region_name="eu-central-1")
    return client, Stubber(client)


# --- DNS record builders (pure) ---------------------------------------------


def test_dkim_cname_records_target_easy_dkim() -> None:
    records = ts.dkim_cname_records("acme.example", ["t1", "t2", "t3"])

    assert [r.type for r in records] == ["CNAME", "CNAME", "CNAME"]
    assert records[0].name == "t1._domainkey.acme.example"
    assert records[0].value == "t1.dkim.amazonses.com"


def test_spf_record_includes_amazon_ses() -> None:
    record = ts.spf_record("acme.example")

    assert record.type == "TXT"
    assert record.name == "acme.example"
    assert "include:amazonses.com" in record.value


def test_dmarc_record_is_a_policy_txt_at_the_dmarc_label() -> None:
    record = ts.dmarc_record("acme.example")

    assert record.type == "TXT"
    assert record.name == "_dmarc.acme.example"
    assert record.value.startswith("v=DMARC1")


def test_mail_from_records_suggest_a_subdomain_mx_and_spf() -> None:
    records = ts.mail_from_records("acme.example", "eu-central-1")

    types = {r.type for r in records}
    assert {"MX", "TXT"}.issubset(types)
    assert any("feedback-smtp.eu-central-1.amazonses.com" in r.value for r in records)
    assert all(r.name.startswith("mail.acme.example") for r in records)


def test_build_dns_records_covers_dkim_spf_and_dmarc() -> None:
    records = ts.build_dns_records("acme.example", ["t1", "t2", "t3"], "eu-central-1")

    pairs = {(r.type, r.name) for r in records}
    assert ("CNAME", "t1._domainkey.acme.example") in pairs
    assert ("TXT", "acme.example") in pairs
    assert ("TXT", "_dmarc.acme.example") in pairs


# --- identity provisioning (idempotent) -------------------------------------


def test_ensure_identity_creates_a_tagged_identity_when_missing(
    sesv2: tuple[object, Stubber],
) -> None:
    client, stubber = sesv2
    stubber.add_client_error("get_email_identity", service_error_code="NotFoundException")
    expected_tags = [{"Key": k, "Value": v} for k, v in standard_tags("staging").items()]
    stubber.add_response(
        "create_email_identity",
        {
            "IdentityType": "DOMAIN",
            "VerifiedForSendingStatus": False,
            "DkimAttributes": {"Status": "PENDING", "Tokens": ["t1", "t2", "t3"]},
        },
        {"EmailIdentity": "acme.example", "Tags": expected_tags},
    )

    with stubber:
        response, created = ts.ensure_identity(client, "acme.example", standard_tags("staging"))

    assert created is True
    assert response["DkimAttributes"]["Tokens"] == ["t1", "t2", "t3"]
    stubber.assert_no_pending_responses()


def test_ensure_identity_is_idempotent_when_already_present(
    sesv2: tuple[object, Stubber],
) -> None:
    client, stubber = sesv2
    stubber.add_response(
        "get_email_identity",
        {
            "IdentityType": "DOMAIN",
            "VerifiedForSendingStatus": True,
            "DkimAttributes": {"Status": "SUCCESS", "Tokens": ["t1", "t2", "t3"]},
        },
        {"EmailIdentity": "acme.example"},
    )

    with stubber:
        response, created = ts.ensure_identity(client, "acme.example", standard_tags("staging"))

    assert created is False
    assert response["VerifiedForSendingStatus"] is True
    stubber.assert_no_pending_responses()  # no create_email_identity call was issued


# --- DKIM status polling -----------------------------------------------------


def test_poll_stops_immediately_when_already_verified() -> None:
    initial = {
        "VerifiedForSendingStatus": True,
        "DkimAttributes": {"Status": "SUCCESS", "Tokens": ["t1"]},
    }
    sleeps: list[float] = []
    out = io.StringIO()

    status, verified, tokens = ts.poll_dkim_status(
        None, "acme.example", initial, attempts=3, interval=5, sleeper=sleeps.append, out=out
    )

    assert (status, verified, tokens) == ("SUCCESS", True, ["t1"])
    assert sleeps == []  # terminal on the first check, never slept
    assert "acme.example" in out.getvalue()


def test_poll_loops_and_sleeps_between_checks_while_pending(
    sesv2: tuple[object, Stubber],
) -> None:
    client, stubber = sesv2
    pending = {
        "VerifiedForSendingStatus": False,
        "DkimAttributes": {"Status": "PENDING", "Tokens": ["t1"]},
    }
    # Check 1 uses the initial dict; checks 2 and 3 re-read the identity.
    stubber.add_response("get_email_identity", pending, {"EmailIdentity": "acme.example"})
    stubber.add_response("get_email_identity", pending, {"EmailIdentity": "acme.example"})
    sleeps: list[float] = []

    with stubber:
        status, verified, _ = ts.poll_dkim_status(
            client,
            "acme.example",
            pending,
            attempts=3,
            interval=5,
            sleeper=sleeps.append,
            out=io.StringIO(),
        )

    assert (status, verified) == ("PENDING", False)
    assert sleeps == [5, 5]
    stubber.assert_no_pending_responses()


# --- sandbox status ----------------------------------------------------------


def test_account_in_sandbox_when_production_access_disabled(
    sesv2: tuple[object, Stubber],
) -> None:
    client, stubber = sesv2
    stubber.add_response("get_account", {"ProductionAccessEnabled": False})

    with stubber:
        assert ts.account_in_sandbox(client) is True


def test_account_out_of_sandbox_when_production_access_enabled(
    sesv2: tuple[object, Stubber],
) -> None:
    client, stubber = sesv2
    stubber.add_response("get_account", {"ProductionAccessEnabled": True})

    with stubber:
        assert ts.account_in_sandbox(client) is False


# --- config resolution -------------------------------------------------------


def test_resolve_config_prefers_flags_over_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "from-env")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_PROFILE", "env-profile")

    args = ts.parse_args(["acme", "--env", "prod", "--region", "eu-west-1", "--profile", "sso"])
    config = ts.resolve_config(args)

    assert config.environment == "prod"
    assert config.region == "eu-west-1"
    assert config.profile == "sso"


def test_resolve_config_requires_an_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(ts.TenantSetupError):
        ts.resolve_config(ts.parse_args(["acme"]))


# --- orchestration -----------------------------------------------------------


def test_run_setup_emits_records_and_reports_sandbox(sesv2: tuple[object, Stubber]) -> None:
    client, stubber = sesv2
    tenant = resolve_tenant("acme")
    stubber.add_response(
        "get_email_identity",
        {
            "IdentityType": "DOMAIN",
            "VerifiedForSendingStatus": False,
            "DkimAttributes": {"Status": "PENDING", "Tokens": ["t1", "t2", "t3"]},
        },
        {"EmailIdentity": "acme.example"},
    )
    stubber.add_response("get_account", {"ProductionAccessEnabled": False})
    out = io.StringIO()
    config = ts.SetupConfig(environment="staging", region="eu-central-1", profile=None)

    with stubber:
        result = ts.run_setup(
            config, tenant, client=client, attempts=1, interval=0, sleeper=lambda _s: None, out=out
        )

    assert result.in_sandbox is True
    assert len(result.domains) == 1
    assert result.domains[0].tokens == ("t1", "t2", "t3")

    text = out.getvalue()
    assert "t1._domainkey.acme.example" in text  # DKIM CNAME emitted
    assert "v=DMARC1" in text  # DMARC guidance emitted
    assert "sandbox" in text.lower()  # sandbox status reported
    assert "cost" in text.lower()  # cost is flagged
    stubber.assert_no_pending_responses()


# --- CLI entrypoint ----------------------------------------------------------


def test_main_returns_nonzero_on_unknown_tenant(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")

    exit_code = ts.main(["nope"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err
    assert "nope" in captured.err


def test_main_reports_a_missing_environment_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    exit_code = ts.main(["acme"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err


def test_main_returns_zero_on_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setattr(ts, "build_client", lambda config: object())
    monkeypatch.setattr(
        ts,
        "run_setup",
        lambda *a, **k: ts.SetupResult(tenant="acme", domains=(), in_sandbox=True),
    )

    exit_code = ts.main(["acme"])

    assert exit_code == 0
    assert "acme" in capsys.readouterr().out
