"""Operator ``tenant-setup`` CLI — SES identity + Easy DKIM + Cloudflare DNS guidance.

This is an out-of-loop tool: it touches real AWS only when a human runs it. In the
Ralph/``verify.sh`` loop its boto3 calls are mocked, so every external effect stays
behind an injectable seam (the ``client`` / ``session_factory`` arguments) and this
module never reads ``os.environ`` directly — config flows through ``config.Settings``.

For each of a tenant's ``from_domains`` it idempotently creates (or looks up) the SES
domain identity with the standard tag set, retrieves its Easy-DKIM tokens, prints
**Cloudflare-ready** DNS records (3 DKIM ``CNAME``s plus recommended SPF/DMARC ``TXT``
records and a custom MAIL FROM suggestion), polls DKIM verification status, and reports
whether the account is still in the SES sandbox along with the steps to leave it.

AWS auth uses the boto3 default credential chain, so ``aws sso login --profile
<profile>`` is the only operator prerequisite; no static keys are read or stored.
Operators see friendly one-line errors and a non-zero exit, never a traceback.
"""

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TextIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from notifications.config import Settings
from notifications.tags import standard_tags
from notifications.tenants import Tenant, UnknownTenant, resolve_tenant

# Easy DKIM publishes three CNAMEs of the form ``<token>._domainkey.<domain>`` that
# point at ``<token>.dkim.amazonses.com``; this is the value suffix.
DKIM_CNAME_SUFFIX = "dkim.amazonses.com"

# DKIM statuses past which polling cannot make further progress in this run.
_TERMINAL_DKIM_STATUSES = frozenset({"SUCCESS", "FAILED"})

# One status read per run by default — the tool is idempotent, so an operator simply
# re-runs it later instead of blocking on a long verification wait.
DEFAULT_POLL_ATTEMPTS = 1
DEFAULT_POLL_INTERVAL_SECONDS = 5.0

ClientFactory = Callable[..., Any]
Sleeper = Callable[[float], None]


class TenantSetupError(Exception):
    """An operator-facing setup failure. ``main`` prints it and exits non-zero."""


@dataclass(frozen=True)
class SetupConfig:
    """The resolved target: environment, region, and optional AWS profile."""

    environment: str
    region: str
    profile: str | None


@dataclass(frozen=True)
class DnsRecord:
    """One Cloudflare-ready DNS record an operator pastes into the zone."""

    type: str
    name: str
    value: str
    note: str = ""


@dataclass(frozen=True)
class DomainSetup:
    """The outcome of provisioning one domain identity."""

    domain: str
    created: bool
    tokens: tuple[str, ...]
    dkim_status: str
    verified_for_sending: bool
    records: tuple[DnsRecord, ...]


@dataclass(frozen=True)
class SetupResult:
    """The aggregate outcome across a tenant's domains plus account sandbox state."""

    tenant: str
    in_sandbox: bool
    domains: tuple[DomainSetup, ...] = field(default_factory=tuple)


# --- argument / config resolution -------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the operator CLI flags.

    Flags override the matching environment variable read by ``config.Settings``:
    ``--env``/``ENVIRONMENT``, ``--region``/``AWS_REGION`` (default ``eu-central-1``),
    and ``--profile``/``AWS_PROFILE``.
    """
    parser = argparse.ArgumentParser(
        prog="tenant-setup",
        description=(
            "Provision SES domain identities and Easy DKIM for a tenant and print "
            "Cloudflare-ready DNS records, verification status, and sandbox guidance."
        ),
    )
    parser.add_argument("tenant", help="Tenant slug from the registry, e.g. acme.")
    parser.add_argument(
        "--env",
        "--environment",
        dest="env",
        default=None,
        help="Deployment target, e.g. staging or prod (overrides ENVIRONMENT).",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region (overrides AWS_REGION; default eu-central-1).",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Named AWS profile for a local SSO session (overrides AWS_PROFILE).",
    )
    parser.add_argument(
        "--poll-attempts",
        type=int,
        default=DEFAULT_POLL_ATTEMPTS,
        help="How many times to read DKIM verification status (default 1).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds to wait between status reads (default 5).",
    )
    return parser.parse_args(argv)


def resolve_config(args: argparse.Namespace) -> SetupConfig:
    """Resolve the target, letting CLI flags override the environment.

    ``config.Settings`` is the single reader of the environment; a missing
    ``ENVIRONMENT`` is reported as a friendly ``TenantSetupError`` rather than a
    pydantic traceback.
    """
    overrides: dict[str, str] = {}
    if args.env is not None:
        overrides["environment"] = args.env
    try:
        settings = Settings(**overrides)
    except ValidationError as exc:
        raise TenantSetupError(
            "ENVIRONMENT is required: pass --env or set the ENVIRONMENT variable."
        ) from exc

    return SetupConfig(
        environment=settings.environment,
        region=args.region or settings.aws_region,
        profile=args.profile or settings.aws_profile,
    )


# --- DNS record builders (pure) ---------------------------------------------


def dkim_cname_records(domain: str, tokens: Sequence[str]) -> list[DnsRecord]:
    """Build the three Easy-DKIM ``CNAME`` records for ``domain``."""
    return [
        DnsRecord(
            type="CNAME",
            name=f"{token}._domainkey.{domain}",
            value=f"{token}.{DKIM_CNAME_SUFFIX}",
            note="DKIM",
        )
        for token in tokens
    ]


def spf_record(domain: str) -> DnsRecord:
    """Recommended SPF ``TXT`` authorizing Amazon SES for ``domain``."""
    return DnsRecord(
        type="TXT",
        name=domain,
        value="v=spf1 include:amazonses.com ~all",
        note="SPF (merge with any existing SPF record — only one is allowed)",
    )


def dmarc_record(domain: str) -> DnsRecord:
    """Recommended starter DMARC ``TXT`` (monitor-only ``p=none``) for ``domain``."""
    return DnsRecord(
        type="TXT",
        name=f"_dmarc.{domain}",
        value=f"v=DMARC1; p=none; rua=mailto:dmarc@{domain}",
        note="DMARC (start at p=none, tighten to quarantine/reject once aligned)",
    )


def mail_from_records(domain: str, region: str) -> list[DnsRecord]:
    """Suggested custom MAIL FROM records on the ``mail.<domain>`` subdomain."""
    mail_from = f"mail.{domain}"
    return [
        DnsRecord(
            type="MX",
            name=mail_from,
            value=f"10 feedback-smtp.{region}.amazonses.com",
            note="custom MAIL FROM (optional; improves SPF alignment)",
        ),
        DnsRecord(
            type="TXT",
            name=mail_from,
            value="v=spf1 include:amazonses.com ~all",
            note="custom MAIL FROM SPF",
        ),
    ]


def build_dns_records(domain: str, tokens: Sequence[str], region: str) -> list[DnsRecord]:
    """Assemble the full Cloudflare-ready record set for ``domain``."""
    return [
        *dkim_cname_records(domain, tokens),
        spf_record(domain),
        dmarc_record(domain),
        *mail_from_records(domain, region),
    ]


# --- AWS-facing operations ---------------------------------------------------


def build_client(config: SetupConfig, *, session_factory: ClientFactory = boto3.Session) -> Any:
    """Construct a region/profile-bound SESv2 client via the default credential chain."""
    session = session_factory(profile_name=config.profile, region_name=config.region)
    return session.client("sesv2")


def ensure_identity(client: Any, domain: str, tags: dict[str, str]) -> tuple[dict[str, Any], bool]:
    """Look up the SES domain identity, creating it (tagged) if absent.

    Returns ``(identity, created)``. Idempotent: an existing identity is returned
    untouched, so re-running for an already verified domain issues no writes.
    """
    try:
        return client.get_email_identity(EmailIdentity=domain), False
    except client.exceptions.NotFoundException:
        tag_list = [{"Key": key, "Value": value} for key, value in tags.items()]
        response = client.create_email_identity(EmailIdentity=domain, Tags=tag_list)
        return response, True


def poll_dkim_status(
    client: Any,
    domain: str,
    initial: dict[str, Any],
    *,
    attempts: int,
    interval: float,
    sleeper: Sleeper,
    out: TextIO,
) -> tuple[str, bool, list[str]]:
    """Report DKIM verification progress, stopping early on a terminal status.

    The first check reads ``initial`` (already fetched by ``ensure_identity``) so a
    single-attempt run makes no extra AWS call; later checks re-read the identity.
    """
    identity = initial
    status, verified, tokens = "UNKNOWN", False, []
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            identity = client.get_email_identity(EmailIdentity=domain)
        dkim = identity.get("DkimAttributes", {})
        status = dkim.get("Status", "UNKNOWN")
        tokens = list(dkim.get("Tokens", []))
        verified = bool(identity.get("VerifiedForSendingStatus", False))
        print(
            f"  [{domain}] DKIM {status}, verified-for-sending={verified} "
            f"(check {attempt}/{attempts})",
            file=out,
        )
        if verified or status in _TERMINAL_DKIM_STATUSES:
            break
        if attempt < attempts:
            sleeper(interval)
    return status, verified, tokens


def account_in_sandbox(client: Any) -> bool:
    """Return whether the SES account is still sandboxed (production access disabled)."""
    account = client.get_account()
    return not bool(account.get("ProductionAccessEnabled", False))


def setup_domain(
    client: Any,
    domain: str,
    *,
    environment: str,
    region: str,
    attempts: int,
    interval: float,
    sleeper: Sleeper,
    out: TextIO,
) -> DomainSetup:
    """Provision one domain identity and return its records and verification state."""
    identity, created = ensure_identity(client, domain, standard_tags(environment))
    status, verified, tokens = poll_dkim_status(
        client, domain, identity, attempts=attempts, interval=interval, sleeper=sleeper, out=out
    )
    records = build_dns_records(domain, tokens, region)
    return DomainSetup(
        domain=domain,
        created=created,
        tokens=tuple(tokens),
        dkim_status=status,
        verified_for_sending=verified,
        records=tuple(records),
    )


# --- presentation ------------------------------------------------------------


def _print_records(setup: DomainSetup, out: TextIO) -> None:
    """Print one domain's Cloudflare-ready records as an aligned table."""
    verb = "created" if setup.created else "found existing"
    print(f"  identity {verb}; add these records in Cloudflare (manual entry, no API):", file=out)
    for record in setup.records:
        line = f"    {record.type:<5} {record.name}  ->  {record.value}"
        if record.note:
            line += f"   ({record.note})"
        print(line, file=out)


def _print_sandbox_guidance(in_sandbox: bool, out: TextIO) -> None:
    """Print SES sandbox status, the path to production, and cost flags."""
    print("\nAccount status:", file=out)
    if in_sandbox:
        print("  SES is in the SANDBOX: you can only send to verified addresses.", file=out)
        print("  To request production access:", file=out)
        print(
            "    SES console -> Account dashboard -> Request production access "
            "(or `aws sesv2 put-account-details`),",
            file=out,
        )
        print("    describing your use case, website, and expected sending volume.", file=out)
    else:
        print("  SES has PRODUCTION access: sending to arbitrary recipients is enabled.", file=out)
    print(
        "  Cost note: domain identities and Easy DKIM are free, but SES bills per "
        "email sent\n"
        "  and for dedicated IPs; leaving the sandbox is free, sending volume is not.",
        file=out,
    )


def run_setup(
    config: SetupConfig,
    tenant: Tenant,
    *,
    client: Any,
    attempts: int = DEFAULT_POLL_ATTEMPTS,
    interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    sleeper: Sleeper = time.sleep,
    out: TextIO | None = None,
) -> SetupResult:
    """Provision every domain for ``tenant`` and report DNS, status, and sandbox state."""
    out = out if out is not None else sys.stdout
    domains: list[DomainSetup] = []
    for domain in tenant.from_domains:
        print(f"\nDomain {domain}:", file=out)
        setup = setup_domain(
            client,
            domain,
            environment=config.environment,
            region=config.region,
            attempts=attempts,
            interval=interval,
            sleeper=sleeper,
            out=out,
        )
        _print_records(setup, out)
        domains.append(setup)

    in_sandbox = account_in_sandbox(client)
    _print_sandbox_guidance(in_sandbox, out)
    return SetupResult(tenant=tenant.slug, in_sandbox=in_sandbox, domains=tuple(domains))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: returns 0 on success, 1 on a handled failure."""
    args = parse_args(argv)
    try:
        config = resolve_config(args)
        tenant = resolve_tenant(args.tenant)
        client = build_client(config)
        result = run_setup(
            config,
            tenant,
            client=client,
            attempts=args.poll_attempts,
            interval=args.poll_interval,
        )
    except (TenantSetupError, UnknownTenant) as exc:
        print(f"tenant-setup failed: {exc}", file=sys.stderr)
        return 1
    except (BotoCoreError, ClientError) as exc:  # AWS/credential errors, friendly one-liner
        print(f"tenant-setup failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nDone. Tenant {result.tenant}: {len(result.domains)} domain(s) processed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
