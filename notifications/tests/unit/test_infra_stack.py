"""Offline synthesis tests for the Troposphere stack — never deploys.

Asserts the synthesized CloudFormation contains the delivery queue, Lambda
function, and IAM role, that every resource carries the standard tag set, and
that the Lambda's environment includes ENVIRONMENT.
"""

import json
from typing import Any

from notifications.infra.stack import build_template
from notifications.tags import standard_tags
from notifications.tenants import TENANTS

# Some resource types do not accept tags in CloudFormation, so they are excluded
# from the every-resource-is-tagged invariant below.
_TAGLESS_TYPES = {"AWS::SES::ConfigurationSet", "AWS::Lambda::EventSourceMapping"}


def _resources_of_type(resources: dict[str, Any], type_: str) -> list[dict[str, Any]]:
    return [r for r in resources.values() if r["Type"] == type_]


def _only(resources: dict[str, Any], type_: str) -> dict[str, Any]:
    matches = _resources_of_type(resources, type_)
    assert len(matches) == 1, f"expected exactly one {type_}, found {len(matches)}"
    return matches[0]


def _synthesize(environment: str) -> dict[str, Any]:
    return json.loads(build_template(environment).to_json())


def _tags_as_dict(resource: dict[str, Any]) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in resource["Properties"].get("Tags", [])}


def test_stack_synthesizes_the_core_delivery_resources() -> None:
    resources = _synthesize("staging")["Resources"]
    types = {resource["Type"] for resource in resources.values()}

    assert "AWS::SQS::Queue" in types
    assert "AWS::Lambda::Function" in types
    assert "AWS::IAM::Role" in types


def test_every_taggable_resource_carries_the_standard_tag_set() -> None:
    resources = _synthesize("staging")["Resources"]
    expected = standard_tags("staging")

    for name, resource in resources.items():
        if resource["Type"] in _TAGLESS_TYPES:
            continue
        assert _tags_as_dict(resource) == expected, f"{name} is missing standard tags"


def test_stack_creates_one_configuration_set_per_tenant_with_the_derived_name() -> None:
    resources = _synthesize("staging")["Resources"]
    config_sets = [r for r in resources.values() if r["Type"] == "AWS::SES::ConfigurationSet"]

    names = {cs["Properties"]["Name"] for cs in config_sets}

    assert len(config_sets) == len(TENANTS)
    assert names == {f"{slug}-staging" for slug in TENANTS}


def test_lambda_environment_includes_environment_variable() -> None:
    resources = _synthesize("prod")["Resources"]
    functions = [r for r in resources.values() if r["Type"] == "AWS::Lambda::Function"]

    assert len(functions) == 1
    variables = functions[0]["Properties"]["Environment"]["Variables"]
    assert variables["ENVIRONMENT"] == "prod"


def test_tags_thread_the_environment_through() -> None:
    resources = _synthesize("prod")["Resources"]

    for resource in resources.values():
        if resource["Type"] in _TAGLESS_TYPES:
            continue
        assert _tags_as_dict(resource)["environment"] == "prod"


def test_stack_provisions_a_dead_letter_queue() -> None:
    resources = _synthesize("staging")["Resources"]
    queues = _resources_of_type(resources, "AWS::SQS::Queue")

    names = {q["Properties"]["QueueName"] for q in queues}

    assert len(queues) == 2
    assert "notification-engine-delivery-dlq-staging" in names


def test_delivery_queue_redrives_to_the_dlq_after_three_receives() -> None:
    resources = _synthesize("staging")["Resources"]
    delivery_queue = resources["DeliveryQueue"]

    redrive = delivery_queue["Properties"]["RedrivePolicy"]

    assert redrive["maxReceiveCount"] == 3
    assert redrive["deadLetterTargetArn"] == {"Fn::GetAtt": ["DeliveryDeadLetterQueue", "Arn"]}


def test_function_sets_a_timeout_and_memory_above_the_aws_defaults() -> None:
    properties = _synthesize("staging")["Resources"]["DeliveryFunction"]["Properties"]

    # The AWS defaults (3s / 128MB) are too tight for a cold start plus an SES
    # round-trip — the function timed out before sending until these were set.
    assert properties["Timeout"] >= 15
    assert properties["MemorySize"] >= 256


def test_delivery_queue_visibility_timeout_covers_the_function_timeout() -> None:
    resources = _synthesize("staging")["Resources"]
    visibility = resources["DeliveryQueue"]["Properties"]["VisibilityTimeout"]
    timeout = resources["DeliveryFunction"]["Properties"]["Timeout"]

    # SQS requires visibility >= function timeout; keep headroom (AWS recommends
    # ~6x) so an in-flight batch is never redelivered as a duplicate mid-processing.
    assert visibility >= timeout * 6


def test_event_source_mapping_reports_batch_item_failures_with_conservative_scaling() -> None:
    resources = _synthesize("staging")["Resources"]
    esm = _only(resources, "AWS::Lambda::EventSourceMapping")["Properties"]

    assert esm["FunctionResponseTypes"] == ["ReportBatchItemFailures"]
    assert esm["EventSourceArn"] == {"Fn::GetAtt": ["DeliveryQueue", "Arn"]}
    assert esm["BatchSize"] >= 1
    assert "MaximumBatchingWindowInSeconds" in esm
    assert esm["ScalingConfig"]["MaximumConcurrency"] == 2


def test_maximum_concurrency_is_configurable() -> None:
    from notifications.infra.stack import build_template

    resources = json.loads(build_template("staging", maximum_concurrency=7).to_json())["Resources"]
    esm = _only(resources, "AWS::Lambda::EventSourceMapping")["Properties"]

    assert esm["ScalingConfig"]["MaximumConcurrency"] == 7


def _delivery_policy_statements(environment: str) -> list[dict[str, Any]]:
    resources = _synthesize(environment)["Resources"]
    role = resources["DeliveryFunctionRole"]
    return role["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]


def _statement(statements: list[dict[str, Any]], sid: str) -> dict[str, Any]:
    return next(s for s in statements if s["Sid"] == sid)


def test_iam_scopes_send_email_to_the_tenant_configuration_sets() -> None:
    statements = _delivery_policy_statements("staging")
    send = _statement(statements, "SendThroughTenantConfigurationSets")

    assert send["Action"] == "ses:SendEmail"
    assert len(send["Resource"]) == len(TENANTS)
    for resource in send["Resource"]:
        assert "configuration-set/" in resource["Fn::Sub"]
        assert "-staging" in resource["Fn::Sub"]


def test_iam_allows_draining_the_source_queue_and_parking_in_the_dlq() -> None:
    statements = _delivery_policy_statements("staging")

    drain = _statement(statements, "DrainDeliveryQueue")
    assert set(drain["Action"]) == {
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
    }
    assert drain["Resource"] == {"Fn::GetAtt": ["DeliveryQueue", "Arn"]}

    park = _statement(statements, "ParkPoisonRecordsInDlq")
    assert park["Action"] == "sqs:SendMessage"
    assert park["Resource"] == {"Fn::GetAtt": ["DeliveryDeadLetterQueue", "Arn"]}


def test_iam_allows_writing_cloudwatch_logs() -> None:
    statements = _delivery_policy_statements("staging")
    logs = _statement(statements, "WriteLogs")

    assert set(logs["Action"]) == {
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
    }


def test_lambda_code_references_the_packaged_s3_artifact() -> None:
    document = _synthesize("staging")

    parameters = document.get("Parameters", {})
    assert "LambdaCodeS3Bucket" in parameters
    assert "LambdaCodeS3Key" in parameters

    code = document["Resources"]["DeliveryFunction"]["Properties"]["Code"]
    assert code == {
        "S3Bucket": {"Ref": "LambdaCodeS3Bucket"},
        "S3Key": {"Ref": "LambdaCodeS3Key"},
    }
    # The placeholder inline-zip stub must be gone so the real handler is deployed.
    assert "ZipFile" not in code


def test_lambda_environment_carries_the_dlq_url() -> None:
    resources = _synthesize("staging")["Resources"]
    variables = resources["DeliveryFunction"]["Properties"]["Environment"]["Variables"]

    assert variables["DELIVERY_DLQ_URL"] == {"Ref": "DeliveryDeadLetterQueue"}


def test_stack_exports_the_delivery_queue_url_as_an_output() -> None:
    outputs = _synthesize("staging").get("Outputs", {})

    assert "DeliveryQueueUrl" in outputs
    assert outputs["DeliveryQueueUrl"]["Value"] == {"Ref": "DeliveryQueue"}
