"""Deploy the LangGraph streaming math agent to Amazon Bedrock AgentCore Runtime.

This mirrors the workflow shown in the official streaming tutorial notebook:
  - Runtime.configure(...)
  - Runtime.launch()
  - Poll Runtime.status() until READY

Prereqs:
  - AWS credentials in environment (or IAM role)
  - Docker available to build/push the image
  - Bedrock AgentCore Starter Toolkit installed (already in this repo's deps)

Usage:
  python langgraph_streaming/deploy_to_agentcore_runtime.py \
    --agent-name langgraph_math_streaming
"""

from __future__ import annotations

import argparse
import time

from bedrock_agentcore_starter_toolkit import Runtime
from boto3.session import Session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent-name",
        default="langgraph_math_streaming",
        help="AgentCore agent runtime name to create/update",
    )
    parser.add_argument(
        "--region",
        default="us-west-2",
        help="AWS region (default: boto3 Session region)",
    )
    parser.add_argument(
        "--streaming-entrypoint",
        default="langgraph_streaming/agentcore_langgraph_math_streaming.py",
        help="Python entrypoint file for AgentCore Runtime",
    )
    parser.add_argument(
        "--requirements-file",
        default="langgraph_streaming/requirements.runtime.txt",
        help="pip requirements file to package into the runtime image",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for runtime to reach READY and print status transitions",
    )
    args = parser.parse_args()

    session = Session()
    region = args.region or session.region_name
    if not region:
        raise SystemExit(
            "No AWS region found. Set AWS_REGION/AWS_DEFAULT_REGION or pass --region."
        )

    agentcore_runtime = Runtime()

    configure_result = agentcore_runtime.configure(
        entrypoint=args.streaming_entrypoint,
        auto_create_execution_role=True,
        auto_create_ecr=True,
        requirements_file=args.requirements_file,
        region=region,
        agent_name=args.agent_name,
    )
    print("Configured:", configure_result)

    launch_result = agentcore_runtime.launch()
    print("Launched:")
    print("  agent_arn:", launch_result.agent_arn)
    print("  agent_id:", launch_result.agent_id)
    print("  ecr_uri:", launch_result.ecr_uri)

    if not args.wait:
        return 0

    end_status = {"READY", "CREATE_FAILED", "DELETE_FAILED", "UPDATE_FAILED"}
    while True:
        status_response = agentcore_runtime.status()
        status = status_response.endpoint.get("status")
        print("Status:", status)
        if status in end_status:
            break
        time.sleep(10)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
