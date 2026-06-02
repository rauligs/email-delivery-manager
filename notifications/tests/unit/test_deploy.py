"""Offline tests for the operator ``deploy`` CLI.

All boto3 and subprocess calls are mocked: these tests assert that the template
is synthesized, that the Lambda artifact is packaged, and that the
``aws cloudformation deploy`` command and its parameters are correct. No real
AWS, no network, no tracebacks reach the operator.
"""

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from notifications import deploy
from notifications.tags import standard_tags


class _RecordingRunner:
    """A fake ``subprocess.run`` that records each command and returns success."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, command: list[str], **_kwargs: Any) -> SimpleNamespace:
        self.calls.append(command)
        return SimpleNamespace(returncode=self.returncode, stdout="", stderr="")

    def command_starting_with(self, *prefix: str) -> list[str]:
        for command in self.calls:
            if command[: len(prefix)] == list(prefix):
                return command
        raise AssertionError(f"no command starting with {prefix} in {self.calls}")


# --- synthesis ---------------------------------------------------------------


def test_synthesize_template_writes_cloudformation_json(tmp_path: Path) -> None:
    destination = tmp_path / "template.json"

    deploy.synthesize_template("staging", destination)

    document = json.loads(destination.read_text())
    assert "DeliveryQueue" in document["Resources"]
    assert document["Outputs"]["DeliveryQueueUrl"]["Value"] == {"Ref": "DeliveryQueue"}


# --- config resolution -------------------------------------------------------


def _args(env=None, region=None, profile=None, artifact_bucket=None) -> SimpleNamespace:
    return SimpleNamespace(env=env, region=region, profile=profile, artifact_bucket=artifact_bucket)


def test_resolve_config_prefers_flags_over_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "from-env")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_PROFILE", "env-profile")
    monkeypatch.setenv("DEPLOY_ARTIFACT_BUCKET", "env-bucket")

    config = deploy.resolve_config(
        _args(env="prod", region="eu-west-1", profile="sso", artifact_bucket="flag-bucket")
    )

    assert config.environment == "prod"
    assert config.region == "eu-west-1"
    assert config.profile == "sso"
    assert config.artifact_bucket == "flag-bucket"


def test_resolve_config_falls_back_to_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DEPLOY_ARTIFACT_BUCKET", "env-bucket")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    config = deploy.resolve_config(_args())

    assert config.environment == "staging"
    assert config.region == "eu-central-1"  # config.py default
    assert config.profile is None
    assert config.artifact_bucket == "env-bucket"


def test_resolve_config_requires_an_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(deploy.DeployError):
        deploy.resolve_config(_args())


def test_resolve_config_requires_an_artifact_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("DEPLOY_ARTIFACT_BUCKET", raising=False)

    with pytest.raises(deploy.DeployError):
        deploy.resolve_config(_args())


# --- packaging ---------------------------------------------------------------


def test_package_lambda_bundles_handler_templates_and_installs_deps(tmp_path: Path) -> None:
    runner = _RecordingRunner()
    artifact = tmp_path / "lambda.zip"

    result = deploy.package_lambda(tmp_path / "build", artifact, runner=runner)

    names = zipfile.ZipFile(result).namelist()
    assert any(name.endswith("notifications/handler.py") for name in names)
    assert any("templates/acme/welcome.html" in name for name in names)

    # Runtime dependencies are installed into the bundle via a subprocess.
    assert any("pip" in part for command in runner.calls for part in command)


def test_package_lambda_raises_when_dependency_install_fails(tmp_path: Path) -> None:
    runner = _RecordingRunner(returncode=1)

    with pytest.raises(deploy.DeployError):
        deploy.package_lambda(tmp_path / "build", tmp_path / "lambda.zip", runner=runner)


# --- artifact upload ---------------------------------------------------------


def test_artifact_key_is_content_addressed(tmp_path: Path) -> None:
    artifact = tmp_path / "lambda.zip"
    artifact.write_bytes(b"contents")

    key = deploy.artifact_key("staging", artifact)

    assert key.startswith("notification-engine/staging/")
    assert key.endswith(".zip")
    # Identical bytes -> identical key (redeploy is a no-op); different bytes -> new key
    # so CloudFormation detects the change and updates the function.
    assert deploy.artifact_key("staging", artifact) == key
    changed = tmp_path / "changed.zip"
    changed.write_bytes(b"different contents")
    assert deploy.artifact_key("staging", changed) != key


def test_upload_artifact_builds_the_s3_cp_command(tmp_path: Path) -> None:
    runner = _RecordingRunner()
    artifact = tmp_path / "lambda.zip"
    artifact.write_bytes(b"x")

    deploy.upload_artifact(
        artifact_path=artifact,
        bucket="artifacts-bucket",
        key="notification-engine/staging/abc.zip",
        region="eu-central-1",
        profile="sso",
        runner=runner,
    )

    command = runner.command_starting_with("aws", "s3", "cp")
    assert str(artifact) in command
    assert "s3://artifacts-bucket/notification-engine/staging/abc.zip" in command
    assert command[command.index("--region") + 1] == "eu-central-1"
    assert command[command.index("--profile") + 1] == "sso"


def test_upload_artifact_raises_deploy_error_on_failure(tmp_path: Path) -> None:
    runner = _RecordingRunner(returncode=1)
    artifact = tmp_path / "lambda.zip"
    artifact.write_bytes(b"x")

    with pytest.raises(deploy.DeployError):
        deploy.upload_artifact(
            artifact_path=artifact,
            bucket="b",
            key="k",
            region="eu-central-1",
            profile=None,
            runner=runner,
        )


# --- cloudformation deploy ---------------------------------------------------


def test_deploy_stack_builds_the_expected_command(tmp_path: Path) -> None:
    runner = _RecordingRunner()
    template_file = tmp_path / "template.json"
    template_file.write_text("{}")
    tags = standard_tags("staging")

    deploy.deploy_stack(
        stack_name="notification-engine-staging",
        template_file=template_file,
        tags=tags,
        region="eu-central-1",
        profile="sso-staging",
        runner=runner,
    )

    command = runner.command_starting_with("aws", "cloudformation", "deploy")
    assert "--stack-name" in command
    assert command[command.index("--stack-name") + 1] == "notification-engine-staging"
    assert command[command.index("--template-file") + 1] == str(template_file)
    assert command[command.index("--region") + 1] == "eu-central-1"
    assert "CAPABILITY_IAM" in command
    assert command[command.index("--profile") + 1] == "sso-staging"

    tag_args = command[command.index("--tags") + 1 :]
    assert set(f"{k}={v}" for k, v in tags.items()).issubset(set(tag_args))


def test_deploy_stack_passes_the_artifact_location_as_parameter_overrides(
    tmp_path: Path,
) -> None:
    runner = _RecordingRunner()
    template_file = tmp_path / "template.json"
    template_file.write_text("{}")

    deploy.deploy_stack(
        stack_name="notification-engine-staging",
        template_file=template_file,
        tags={},
        region="eu-central-1",
        profile=None,
        parameters={
            "LambdaCodeS3Bucket": "artifacts-bucket",
            "LambdaCodeS3Key": "notification-engine/staging/abc.zip",
        },
        runner=runner,
    )

    command = runner.command_starting_with("aws", "cloudformation", "deploy")
    overrides = command[command.index("--parameter-overrides") + 1 :]
    assert "LambdaCodeS3Bucket=artifacts-bucket" in overrides
    assert "LambdaCodeS3Key=notification-engine/staging/abc.zip" in overrides


def test_deploy_stack_omits_profile_when_not_set(tmp_path: Path) -> None:
    runner = _RecordingRunner()
    template_file = tmp_path / "template.json"
    template_file.write_text("{}")

    deploy.deploy_stack(
        stack_name="notification-engine-staging",
        template_file=template_file,
        tags=standard_tags("staging"),
        region="eu-central-1",
        profile=None,
        runner=runner,
    )

    command = runner.command_starting_with("aws", "cloudformation", "deploy")
    assert "--profile" not in command


def test_deploy_stack_raises_deploy_error_on_failure(tmp_path: Path) -> None:
    runner = _RecordingRunner(returncode=2)
    template_file = tmp_path / "template.json"
    template_file.write_text("{}")

    with pytest.raises(deploy.DeployError):
        deploy.deploy_stack(
            stack_name="notification-engine-staging",
            template_file=template_file,
            tags={},
            region="eu-central-1",
            profile=None,
            runner=runner,
        )


def test_deploy_stack_raises_deploy_error_when_aws_cli_is_missing(tmp_path: Path) -> None:
    def missing(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        raise FileNotFoundError("aws")

    template_file = tmp_path / "template.json"
    template_file.write_text("{}")

    with pytest.raises(deploy.DeployError):
        deploy.deploy_stack(
            stack_name="notification-engine-staging",
            template_file=template_file,
            tags={},
            region="eu-central-1",
            profile=None,
            runner=missing,
        )


# --- stack outputs -----------------------------------------------------------


class _FakeCloudFormation:
    def __init__(self, outputs: list[dict[str, str]]) -> None:
        self._outputs = outputs
        self.described_with: dict[str, Any] | None = None

    def describe_stacks(self, **kwargs: Any) -> dict[str, Any]:
        self.described_with = kwargs
        return {"Stacks": [{"Outputs": self._outputs}]}


class _FakeSession:
    def __init__(self, client: _FakeCloudFormation) -> None:
        self._client = client
        self.created_with: dict[str, Any] | None = None

    def client(self, service_name: str) -> _FakeCloudFormation:
        assert service_name == "cloudformation"
        return self._client


def test_stack_outputs_reads_describe_stacks() -> None:
    cfn = _FakeCloudFormation(
        [
            {"OutputKey": "DeliveryQueueUrl", "OutputValue": "https://sqs/queue"},
            {"OutputKey": "Other", "OutputValue": "value"},
        ]
    )

    captured: dict[str, Any] = {}

    def session_factory(**kwargs: Any) -> _FakeSession:
        captured.update(kwargs)
        return _FakeSession(cfn)

    outputs = deploy.stack_outputs(
        stack_name="notification-engine-prod",
        region="eu-central-1",
        profile="sso",
        session_factory=session_factory,
    )

    assert outputs["DeliveryQueueUrl"] == "https://sqs/queue"
    assert captured == {"profile_name": "sso", "region_name": "eu-central-1"}
    assert cfn.described_with == {"StackName": "notification-engine-prod"}


# --- orchestration -----------------------------------------------------------


def test_run_deploy_synthesizes_packages_deploys_and_returns_outputs() -> None:
    seen_template: dict[str, Any] = {}

    class _CapturingRunner(_RecordingRunner):
        def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
            if command[:3] == ["aws", "cloudformation", "deploy"]:
                path = Path(command[command.index("--template-file") + 1])
                seen_template["document"] = json.loads(path.read_text())
            return super().__call__(command, **kwargs)

    capturing = _CapturingRunner()
    cfn = _FakeCloudFormation([{"OutputKey": "DeliveryQueueUrl", "OutputValue": "https://sqs/q"}])

    config = deploy.DeployConfig(
        environment="staging",
        region="eu-central-1",
        profile=None,
        artifact_bucket="artifacts-bucket",
    )
    outputs = deploy.run_deploy(
        config,
        subprocess_runner=capturing,
        session_factory=lambda **_kw: _FakeSession(cfn),
    )

    # The template was synthesized and handed to the deploy command at call time.
    assert "DeliveryQueue" in seen_template["document"]["Resources"]
    deploy_command = capturing.command_starting_with("aws", "cloudformation", "deploy")
    assert "notification-engine-staging" in deploy_command
    assert outputs["DeliveryQueueUrl"] == "https://sqs/q"

    # The artifact was uploaded to S3 before deploy, and its location was threaded
    # through to CloudFormation so the synthesized Code reference resolves.
    upload = capturing.command_starting_with("aws", "s3", "cp")
    assert any(part.startswith("s3://artifacts-bucket/") for part in upload)
    overrides = deploy_command[deploy_command.index("--parameter-overrides") + 1 :]
    assert "LambdaCodeS3Bucket=artifacts-bucket" in overrides
    assert any(o.startswith("LambdaCodeS3Key=notification-engine/staging/") for o in overrides)
    code = seen_template["document"]["Resources"]["DeliveryFunction"]["Properties"]["Code"]
    assert code == {
        "S3Bucket": {"Ref": "LambdaCodeS3Bucket"},
        "S3Key": {"Ref": "LambdaCodeS3Key"},
    }


# --- CLI entrypoint ----------------------------------------------------------


def test_main_prints_outputs_and_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DEPLOY_ARTIFACT_BUCKET", "artifacts-bucket")
    monkeypatch.setattr(
        deploy,
        "run_deploy",
        lambda *a, **k: {"DeliveryQueueUrl": "https://sqs/queue", "Other": "x"},
    )

    exit_code = deploy.main([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "DeliveryQueueUrl" in out
    assert "https://sqs/queue" in out


def test_main_returns_nonzero_without_traceback_on_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DEPLOY_ARTIFACT_BUCKET", "artifacts-bucket")

    def boom(*_a: Any, **_k: Any) -> None:
        raise deploy.DeployError("cloudformation deploy failed")

    monkeypatch.setattr(deploy, "run_deploy", boom)

    exit_code = deploy.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err
    assert "cloudformation deploy failed" in captured.err


def test_main_reports_a_missing_environment_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    exit_code = deploy.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err
