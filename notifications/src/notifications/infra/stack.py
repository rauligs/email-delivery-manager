"""Troposphere stack for the delivery path.

Synthesizes the resources the engine needs to receive, process, and fail safely:
an SQS delivery queue with a dead-letter queue behind a redrive policy, the
Lambda that drains it, an event-source mapping that asks SQS for partial-batch
responses, and a least-privilege IAM execution role. Every taggable resource
carries the standard tag set, and the Lambda's environment carries ``ENVIRONMENT``
and the DLQ URL so the running code matches the provisioned infrastructure.

This module only *builds* the template; it never deploys.
"""

from troposphere import GetAtt, Output, Parameter, Ref, Sub, Tags, Template
from troposphere.awslambda import (
    Code,
    Environment,
    EventSourceMapping,
    Function,
    ScalingConfig,
)
from troposphere.iam import Policy, Role
from troposphere.ses import ConfigurationSet
from troposphere.sqs import Queue, RedrivePolicy

from notifications.tags import standard_tags
from notifications.tenants import TENANTS, Tenant, configuration_set_name

LAMBDA_RUNTIME = "python3.12"
LAMBDA_HANDLER = "notifications.handler.handler"

# The deploy CLI fills these two parameters with the S3 location of the packaged
# Lambda artifact. Keeping the artifact reference as parameters lets synthesis stay
# pure — no per-deploy bucket/key is baked into the template — while the deploy step
# supplies the concrete, content-addressed object via ``--parameter-overrides``.
LAMBDA_CODE_BUCKET_PARAMETER = "LambdaCodeS3Bucket"
LAMBDA_CODE_KEY_PARAMETER = "LambdaCodeS3Key"

# A poison record is redriven to the DLQ after this many receives, so transient
# retries are bounded and non-retriable records never loop forever.
MAX_RECEIVE_COUNT = 3

# Event-source-mapping tuning. The batching window trades a little latency for
# fewer, fuller invocations; the concurrency cap is deliberately conservative so a
# backlog cannot fan out into an SES-throttling storm. Override per environment.
DEFAULT_BATCH_SIZE = 10
DEFAULT_BATCHING_WINDOW_SECONDS = 5
DEFAULT_MAXIMUM_CONCURRENCY = 2


def _configuration_set_logical_id(tenant: Tenant) -> str:
    """A CloudFormation-safe logical id for a tenant's configuration set."""
    alphanumeric = "".join(part.capitalize() for part in tenant.slug.replace("_", "-").split("-"))
    return f"{alphanumeric}ConfigurationSet"


def _configuration_set_arns(environment: str) -> list[Sub]:
    """The SES configuration-set ARNs the function may send through, one per tenant."""
    return [
        Sub(
            "arn:${AWS::Partition}:ses:${AWS::Region}:${AWS::AccountId}:"
            f"configuration-set/{configuration_set_name(tenant, environment)}"
        )
        for tenant in TENANTS.values()
    ]


def build_template(
    environment: str,
    *,
    maximum_concurrency: int = DEFAULT_MAXIMUM_CONCURRENCY,
) -> Template:
    """Build the CloudFormation template for ``environment``."""
    tags = standard_tags(environment)

    template = Template()
    template.set_description(f"Notification engine delivery path ({environment})")

    code_bucket = template.add_parameter(
        Parameter(
            LAMBDA_CODE_BUCKET_PARAMETER,
            Type="String",
            Description="S3 bucket holding the packaged Lambda deployment artifact.",
        )
    )
    code_key = template.add_parameter(
        Parameter(
            LAMBDA_CODE_KEY_PARAMETER,
            Type="String",
            Description=(
                "S3 key of the packaged Lambda deployment artifact. It is content-addressed, "
                "so a code change yields a new key that CloudFormation uses to update the function."
            ),
        )
    )

    dead_letter_queue = Queue(
        "DeliveryDeadLetterQueue",
        QueueName=f"notification-engine-delivery-dlq-{environment}",
        Tags=Tags(tags),
    )

    delivery_queue = Queue(
        "DeliveryQueue",
        QueueName=f"notification-engine-delivery-{environment}",
        RedrivePolicy=RedrivePolicy(
            deadLetterTargetArn=GetAtt(dead_letter_queue, "Arn"),
            maxReceiveCount=MAX_RECEIVE_COUNT,
        ),
        Tags=Tags(tags),
    )

    execution_role = Role(
        "DeliveryFunctionRole",
        AssumeRolePolicyDocument={
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        },
        Policies=[
            Policy(
                PolicyName="delivery-function-policy",
                PolicyDocument={
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "SendThroughTenantConfigurationSets",
                            "Effect": "Allow",
                            "Action": "ses:SendEmail",
                            "Resource": _configuration_set_arns(environment),
                        },
                        {
                            "Sid": "DrainDeliveryQueue",
                            "Effect": "Allow",
                            "Action": [
                                "sqs:ReceiveMessage",
                                "sqs:DeleteMessage",
                                "sqs:GetQueueAttributes",
                            ],
                            "Resource": GetAtt(delivery_queue, "Arn"),
                        },
                        {
                            "Sid": "ParkPoisonRecordsInDlq",
                            "Effect": "Allow",
                            "Action": "sqs:SendMessage",
                            "Resource": GetAtt(dead_letter_queue, "Arn"),
                        },
                        {
                            "Sid": "WriteLogs",
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": Sub(
                                "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:"
                                f"log-group:/aws/lambda/notification-engine-delivery-{environment}:*"
                            ),
                        },
                    ],
                },
            )
        ],
        Tags=Tags(tags),
    )

    delivery_function = Function(
        "DeliveryFunction",
        FunctionName=f"notification-engine-delivery-{environment}",
        Runtime=LAMBDA_RUNTIME,
        Handler=LAMBDA_HANDLER,
        Role=GetAtt(execution_role, "Arn"),
        Code=Code(S3Bucket=Ref(code_bucket), S3Key=Ref(code_key)),
        Environment=Environment(
            Variables={
                "ENVIRONMENT": environment,
                "DELIVERY_DLQ_URL": Ref(dead_letter_queue),
            }
        ),
        Tags=Tags(tags),
    )

    # Ask SQS for partial-batch reporting so the handler can fail individual
    # records; cap concurrency so a backlog drains gently rather than stampeding.
    event_source_mapping = EventSourceMapping(
        "DeliveryEventSourceMapping",
        EventSourceArn=GetAtt(delivery_queue, "Arn"),
        FunctionName=Ref(delivery_function),
        BatchSize=DEFAULT_BATCH_SIZE,
        MaximumBatchingWindowInSeconds=DEFAULT_BATCHING_WINDOW_SECONDS,
        FunctionResponseTypes=["ReportBatchItemFailures"],
        ScalingConfig=ScalingConfig(MaximumConcurrency=maximum_concurrency),
    )

    template.add_resource(dead_letter_queue)
    template.add_resource(delivery_queue)
    template.add_resource(execution_role)
    template.add_resource(delivery_function)
    template.add_resource(event_source_mapping)

    # One SES configuration set per tenant, named with the same derived
    # ``<slug>-<environment>`` the handler binds each send to. Looping the shared
    # registry keeps the provisioned sets and the running code in lockstep.
    # ``AWS::SES::ConfigurationSet`` does not accept tags, so these resources are
    # intentionally untagged.
    for tenant in TENANTS.values():
        template.add_resource(
            ConfigurationSet(
                _configuration_set_logical_id(tenant),
                Name=configuration_set_name(tenant, environment),
            )
        )

    # The delivery queue URL is what producers enqueue against, so the deploy CLI
    # surfaces it to the operator. ``Ref`` of an SQS queue resolves to its URL.
    template.add_output(
        Output(
            "DeliveryQueueUrl",
            Description="URL of the delivery queue producers enqueue delivery requests to.",
            Value=Ref(delivery_queue),
        )
    )

    return template
