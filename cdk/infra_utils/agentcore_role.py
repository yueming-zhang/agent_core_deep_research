from aws_cdk import (
    aws_iam as iam,
    Stack
)
from constructs import Construct

class AgentCoreRole(iam.Role):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        region = Stack.of(scope).region
        account_id = Stack.of(scope).account
        
        super().__init__(scope, construct_id,
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            inline_policies={
                "AgentCorePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="ECRImageAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ecr:BatchGetImage",
                                "ecr:GetDownloadUrlForLayer",
                                "ecr:BatchCheckLayerAvailability"
                            ],
                            resources=[f"arn:aws:ecr:{region}:{account_id}:repository/*"]
                        ),
                        iam.PolicyStatement(
                            sid="ECRTokenAccess", 
                            effect=iam.Effect.ALLOW,
                            actions=["ecr:GetAuthorizationToken"],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:DescribeLogStreams",
                                "logs:CreateLogGroup"
                            ],
                            resources=[f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["logs:DescribeLogGroups"],
                            resources=[f"arn:aws:logs:{region}:{account_id}:log-group:*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "xray:PutTraceSegments",
                                "xray:PutTelemetryRecords", 
                                "xray:GetSamplingRules",
                                "xray:GetSamplingTargets"
                            ],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["cloudwatch:PutMetricData"],
                            resources=["*"],
                            conditions={
                                "StringEquals": {
                                    "cloudwatch:namespace": "bedrock-agentcore"
                                }
                            }
                        ),
                        iam.PolicyStatement(
                            sid="GetAgentAccessToken",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock-agentcore:GetWorkloadAccessToken",
                                "bedrock-agentcore:GetWorkloadAccessTokenForJWT", 
                                "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                                f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/*"
                            ]
                        ),
                        iam.PolicyStatement(
                            sid="BedrockModelInvocation",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream"
                            ],
                            resources=[
                                "arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:{region}:{account_id}:*"
                            ]
                        ),
                        iam.PolicyStatement(
                            sid="AgentCoreMemoryFullAccess",
                            effect=iam.Effect.ALLOW,
                            actions=["bedrock-agentcore:*"],
                            resources=["arn:aws:bedrock-agentcore:us-west-2:482387069690:memory/DeepResearchAgent-7gZmvrCKCl"]
                        ),
                        iam.PolicyStatement(
                            sid="SSMParameterStoreRead",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ssm:GetParameter",
                                "ssm:GetParameters",
                                "ssm:GetParametersByPath"
                            ],
                            resources=[f"arn:aws:ssm:{region}:{account_id}:parameter/deep_research_scoping_agent/*"]
                        )
                    ]
                )
            },
            **kwargs
        )
