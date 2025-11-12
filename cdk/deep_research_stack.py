from aws_cdk import (
    Stack,
    aws_ecr as ecr,
    aws_bedrockagentcore as bedrockagentcore
)
from constructs import Construct
import sys
import os
from infra_utils.agentcore_role import AgentCoreRole
import warnings
warnings.filterwarnings('ignore', message='Typeguard cannot check.*protocol')


sys.path.append(os.path.join(os.path.dirname(__file__), 'infra_utils'))


class DeepResearchStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Parameters
        agent_name = 'ScopingAgent'

        # # ECR Repository
        # ecr_repository = ecr.Repository(self, "ECRRepository",
        #                                 repository_name=f"{self.stack_name.lower()}-scoping-agent",
        #                                 image_tag_mutability=ecr.TagMutability.MUTABLE,
        #                                 removal_policy=RemovalPolicy.DESTROY,
        #                                 empty_on_delete=True,
        #                                 image_scan_on_push=True
        #                                 )

        # Create AgentCore execution role
        agent_role = AgentCoreRole(self, "AgentCoreRole")

        # Create AgentCore Runtime
        agent_runtime = bedrockagentcore.CfnRuntime(
            self, "AgentRuntime",
            agent_runtime_name=f"{self.stack_name}{agent_name}",
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=bedrockagentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri="482387069690.dkr.ecr.us-west-2.amazonaws.com/deep_research_scoping_agent:latest"
                    #container_uri="482387069690.dkr.ecr.us-west-2.amazonaws.com/basicagentdemo-basic-agent:latest"
                )
            ),
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode='PUBLIC'
            ),
            protocol_configuration="HTTP",
            role_arn=agent_role.role_arn,
            description=f"Basic agent runtime for {self.stack_name}",
            environment_variables={
                "AWS_DEFAULT_REGION": self.region
            }
        )

