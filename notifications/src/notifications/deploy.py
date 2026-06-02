"""Operator ``deploy`` CLI — synthesize, package, and CloudFormation deploy.

This is an out-of-loop tool: it touches real AWS only when a human runs it. In
the Ralph/``verify.sh`` loop its boto3 and subprocess calls are mocked, so this
module keeps every external effect behind an injectable seam (``runner`` and
``session_factory``) and never reads ``os.environ`` directly — config flows
through ``config.Settings``.

Pipeline: resolve config -> synthesize the Troposphere template -> package the
Lambda artifact (handler + embedded templates + runtime deps) -> upload it to S3
under a content-addressed key -> invoke ``aws cloudformation deploy`` with the
standard tag set and the artifact's S3 location as parameter overrides -> print
the stack outputs, including ``DeliveryQueueUrl``.

AWS auth uses the boto3 default credential chain, so ``aws sso login --profile
<profile>`` is the only operator prerequisite; no static keys are read or stored.
Operators see friendly one-line errors and a non-zero exit, never a traceback.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from pydantic import ValidationError

from notifications.config import Settings
from notifications.infra.stack import (
    LAMBDA_CODE_BUCKET_PARAMETER,
    LAMBDA_CODE_KEY_PARAMETER,
    build_template,
)
from notifications.tags import standard_tags

# The package source root (``src/notifications``); its handler and embedded
# templates are what the Lambda artifact bundles.
PACKAGE_ROOT = Path(__file__).resolve().parent

STACK_NAME_PREFIX = "notification-engine"
LAMBDA_CAPABILITY = "CAPABILITY_IAM"

# Runtime dependencies the handler needs that the Lambda runtime does not already
# provide. The python3.12 runtime ships ``boto3``/``botocore`` (excluded here), but
# NOT jinja2, pydantic, or pydantic-settings — the handler imports all three
# (rendering, request validation, settings). ``uv pip install`` resolves their
# transitive deps (pydantic-core, python-dotenv, …) into the bundle automatically.
RUNTIME_DEPENDENCIES = ("jinja2", "pydantic", "pydantic-settings")

# Dependencies are packaged for the Lambda's runtime — python3.12 on the default
# x86_64 architecture — not the operator's machine, so compiled wheels (e.g.
# markupsafe's C speedups) are the correct ones for AWS Lambda.
LAMBDA_PYTHON_VERSION = "3.12"
LAMBDA_PYTHON_PLATFORM = "x86_64-unknown-linux-gnu"

# Every external call is bounded so a hung CLI cannot block an operator forever.
SUBPROCESS_TIMEOUT_SECONDS = 600

# A callable with the shape of ``subprocess.run`` that we actually rely on.
Runner = Callable[..., Any]
SessionFactory = Callable[..., Any]


class DeployError(Exception):
    """An operator-facing deploy failure. ``main`` prints it and exits non-zero."""


@dataclass(frozen=True)
class DeployConfig:
    """The resolved deployment target: environment, region, profile, and artifact bucket."""

    environment: str
    region: str
    profile: str | None
    artifact_bucket: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the operator CLI flags.

    Flags override the matching environment variable read by ``config.Settings``:
    ``--env``/``ENVIRONMENT``, ``--region``/``AWS_REGION`` (default
    ``eu-central-1``), and ``--profile``/``AWS_PROFILE``.
    """
    parser = argparse.ArgumentParser(
        prog="deploy",
        description="Synthesize, package, and CloudFormation-deploy the notification engine.",
    )
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
        help="AWS region to deploy to (overrides AWS_REGION; default eu-central-1).",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Named AWS profile for a local SSO session (overrides AWS_PROFILE).",
    )
    parser.add_argument(
        "--artifact-bucket",
        dest="artifact_bucket",
        default=None,
        help="S3 bucket for the packaged Lambda artifact (overrides DEPLOY_ARTIFACT_BUCKET).",
    )
    return parser.parse_args(argv)


def resolve_config(args: argparse.Namespace) -> DeployConfig:
    """Resolve the deployment target, letting CLI flags override the environment.

    ``config.Settings`` is the single reader of the environment; a ``--env`` flag
    is passed in as an override. A missing environment is reported as a friendly
    ``DeployError`` rather than a pydantic traceback.
    """
    overrides: dict[str, str] = {}
    if args.env is not None:
        overrides["environment"] = args.env
    try:
        settings = Settings(**overrides)
    except ValidationError as exc:
        raise DeployError(
            "ENVIRONMENT is required: pass --env or set the ENVIRONMENT variable."
        ) from exc

    artifact_bucket = args.artifact_bucket or settings.deploy_artifact_bucket
    if not artifact_bucket:
        raise DeployError(
            "a deploy artifact S3 bucket is required: pass --artifact-bucket or set "
            "DEPLOY_ARTIFACT_BUCKET."
        )

    return DeployConfig(
        environment=settings.environment,
        region=args.region or settings.aws_region,
        profile=args.profile or settings.aws_profile,
        artifact_bucket=artifact_bucket,
    )


def synthesize_template(environment: str, destination: Path) -> Path:
    """Synthesize the Troposphere template for ``environment`` to ``destination``."""
    destination.write_text(build_template(environment).to_json())
    return destination


def _run(runner: Runner, command: list[str], *, failure: str) -> None:
    """Run ``command`` with a bounded timeout, raising ``DeployError`` on failure.

    Wraps the three ways an external command fails an operator — a missing
    executable, a timeout, or a non-zero exit — into one friendly error so no
    traceback escapes to the console.
    """
    try:
        result = runner(
            command,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DeployError(f"{failure}: required command not found: {command[0]!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DeployError(f"{failure}: timed out after {SUBPROCESS_TIMEOUT_SECONDS}s") from exc

    if result.returncode != 0:
        raise DeployError(f"{failure} (exit {result.returncode}).")


def package_lambda(
    build_dir: Path | str,
    artifact_path: Path | str,
    *,
    package_root: Path = PACKAGE_ROOT,
    runner: Runner = subprocess.run,
) -> Path:
    """Build the Lambda deployment zip: handler + embedded templates + runtime deps.

    The package source (handler and ``templates/``) is copied under a
    ``notifications`` directory so the deployed ``notifications.handler.handler``
    import path resolves, then runtime dependencies are installed alongside it and
    the whole tree is zipped into ``artifact_path``.
    """
    build_dir = Path(build_dir)
    artifact_path = Path(artifact_path)

    if build_dir.exists():
        shutil.rmtree(build_dir)
    shutil.copytree(
        package_root,
        build_dir / "notifications",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    # ``uv pip install`` is used rather than ``python -m pip``: the project runs in
    # a uv-managed virtualenv that does not ship ``pip``, and uv lets us resolve
    # wheels for the Lambda's platform/version regardless of the operator's OS.
    _run(
        runner,
        [
            "uv",
            "pip",
            "install",
            *RUNTIME_DEPENDENCIES,
            "--target",
            str(build_dir),
            "--python-platform",
            LAMBDA_PYTHON_PLATFORM,
            "--python-version",
            LAMBDA_PYTHON_VERSION,
        ],
        failure="packaging the Lambda dependencies failed",
    )

    return _zip_tree(build_dir, artifact_path)


def _zip_tree(source: Path, artifact_path: Path) -> Path:
    """Zip every file under ``source`` into ``artifact_path`` with relative paths."""
    with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    return artifact_path


def artifact_key(environment: str, artifact_path: Path | str) -> str:
    """A content-addressed S3 key for the packaged artifact.

    Hashing the zip means an unchanged build reuses the same object — a redeploy is
    a no-op — while any code change yields a new key. CloudFormation sees that new
    key as a parameter change and updates the function; a constant key would leave
    the deployed code stale because CloudFormation never re-fetches an unchanged S3
    location.
    """
    digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
    return f"notification-engine/{environment}/{digest}.zip"


def upload_artifact(
    *,
    artifact_path: Path | str,
    bucket: str,
    key: str,
    region: str,
    profile: str | None,
    runner: Runner = subprocess.run,
) -> None:
    """Upload the packaged Lambda artifact to ``s3://bucket/key`` via the AWS CLI.

    This is the S3 staging step the CloudFormation template's ``Code`` reference
    depends on; it runs before ``deploy_stack`` so the object exists when the stack
    points the function at it.
    """
    command = [
        "aws",
        "s3",
        "cp",
        str(artifact_path),
        f"s3://{bucket}/{key}",
        "--region",
        region,
    ]
    if profile:
        command.extend(["--profile", profile])

    _run(runner, command, failure="uploading the Lambda artifact failed")


def deploy_stack(
    *,
    stack_name: str,
    template_file: Path,
    tags: dict[str, str],
    region: str,
    profile: str | None,
    parameters: dict[str, str] | None = None,
    runner: Runner = subprocess.run,
) -> None:
    """Invoke ``aws cloudformation deploy`` with the standard stack-level tags.

    ``CAPABILITY_IAM`` is declared because the stack provisions the Lambda's
    execution role. ``--no-fail-on-empty-changeset`` makes a redeploy with no
    changes a success rather than an error. ``parameters`` are passed through as
    ``--parameter-overrides`` — the engine uses them to point the function at the
    packaged artifact's S3 location.
    """
    command = [
        "aws",
        "cloudformation",
        "deploy",
        "--template-file",
        str(template_file),
        "--stack-name",
        stack_name,
        "--capabilities",
        LAMBDA_CAPABILITY,
        "--region",
        region,
        "--no-fail-on-empty-changeset",
    ]
    if tags:
        command.append("--tags")
        command.extend(f"{key}={value}" for key, value in tags.items())
    if parameters:
        command.append("--parameter-overrides")
        command.extend(f"{key}={value}" for key, value in parameters.items())
    if profile:
        command.extend(["--profile", profile])

    _run(runner, command, failure="cloudformation deploy failed")


def stack_outputs(
    *,
    stack_name: str,
    region: str,
    profile: str | None,
    session_factory: SessionFactory = boto3.Session,
) -> dict[str, str]:
    """Read the deployed stack's outputs via boto3 (default credential chain)."""
    try:
        session = session_factory(profile_name=profile, region_name=region)
        client = session.client("cloudformation")
        response = client.describe_stacks(StackName=stack_name)
    except Exception as exc:  # noqa: BLE001 — surface AWS/botocore errors as friendly text
        raise DeployError(f"reading stack outputs failed: {exc}") from exc

    stacks = response.get("Stacks", [])
    if not stacks:
        raise DeployError(f"stack {stack_name!r} has no outputs to read.")
    return {output["OutputKey"]: output["OutputValue"] for output in stacks[0].get("Outputs", [])}


def run_deploy(
    config: DeployConfig,
    *,
    subprocess_runner: Runner = subprocess.run,
    session_factory: SessionFactory = boto3.Session,
) -> dict[str, str]:
    """Synthesize, package, deploy, and return the stack outputs for ``config``."""
    stack_name = f"{STACK_NAME_PREFIX}-{config.environment}"
    tags = standard_tags(config.environment)

    with tempfile.TemporaryDirectory(prefix="notification-engine-deploy-") as workspace:
        work = Path(workspace)
        template_file = synthesize_template(config.environment, work / "template.json")
        artifact = package_lambda(work / "build", work / "lambda.zip", runner=subprocess_runner)
        key = artifact_key(config.environment, artifact)
        upload_artifact(
            artifact_path=artifact,
            bucket=config.artifact_bucket,
            key=key,
            region=config.region,
            profile=config.profile,
            runner=subprocess_runner,
        )
        deploy_stack(
            stack_name=stack_name,
            template_file=template_file,
            tags=tags,
            region=config.region,
            profile=config.profile,
            parameters={
                LAMBDA_CODE_BUCKET_PARAMETER: config.artifact_bucket,
                LAMBDA_CODE_KEY_PARAMETER: key,
            },
            runner=subprocess_runner,
        )

    return stack_outputs(
        stack_name=stack_name,
        region=config.region,
        profile=config.profile,
        session_factory=session_factory,
    )


def _print_outputs(stack_name: str, outputs: dict[str, str]) -> None:
    """Print the stack outputs, leading with the delivery queue URL."""
    print(f"Deployed {stack_name}. Stack outputs:")
    if not outputs:
        print("  (no outputs)")
        return
    queue_url = outputs.get("DeliveryQueueUrl")
    if queue_url is not None:
        print(f"  DeliveryQueueUrl = {queue_url}")
    for key, value in outputs.items():
        if key != "DeliveryQueueUrl":
            print(f"  {key} = {value}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: returns 0 on success, 1 on a handled failure."""
    args = parse_args(argv)
    try:
        config = resolve_config(args)
        outputs = run_deploy(config)
    except DeployError as exc:
        print(f"deploy failed: {exc}", file=sys.stderr)
        return 1

    _print_outputs(f"{STACK_NAME_PREFIX}-{config.environment}", outputs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
