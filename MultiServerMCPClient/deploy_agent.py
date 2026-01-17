"""Deploy the MultiServerMCPClient LangGraph agent to AgentCore.

This script intentionally has NO CLI arguments.

Behavior:
    - If an AgentCore runtime named `AGENT_NAME` exists: upgrade it.
    - Otherwise: create a new runtime.

Assumptions:
    - `requirements.runtime.txt` exists in the same folder as this file.
    - `agentcore_remote_agent.py` exists in the same folder as this file.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from bedrock_agentcore_starter_toolkit import Runtime
from bedrock_agentcore_starter_toolkit.services.runtime import BedrockAgentCoreClient


REGION = "us-west-2"
AGENT_NAME = "multiserver_mcp_agent"


def _same_dir_path(filename: str) -> Path:
    return Path(__file__).resolve().parent / filename


def _require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    if not path.is_file():
        raise SystemExit(f"Expected a file but found non-file path: {path}")


def _agent_exists() -> bool:
    client = BedrockAgentCoreClient(REGION)
    found = client.find_agent_by_name(AGENT_NAME)
    if found:
        agent_id = found.get("agentRuntimeId")
        agent_arn = found.get("agentRuntimeArn")
        print("Found existing agent runtime:")
        print("  agentRuntimeId:", agent_id)
        print("  agentRuntimeArn:", agent_arn)
        return True
    print("Agent runtime not found; will create a new one:")
    print("  agentRuntimeName:", AGENT_NAME)
    return False


def main() -> int:
    entrypoint = _same_dir_path("agentcore_remote_agent.py")
    requirements_file = _same_dir_path("requirements.runtime.txt")
    _require_file(entrypoint)
    _require_file(requirements_file)

    auto_update_on_conflict = _agent_exists()

    runtime = Runtime()
    configure_result = runtime.configure(
        entrypoint=str(entrypoint),
        auto_create_execution_role=True,
        auto_create_ecr=True,
        requirements_file=str(requirements_file),
        region=REGION,
        agent_name=AGENT_NAME,
        protocol="HTTP",
    )
    print("Configured:", configure_result)

    launch_result = runtime.launch(auto_update_on_conflict=auto_update_on_conflict)
    print("Launched:")
    print("  agent_arn:", launch_result.agent_arn)
    print("  agent_id:", launch_result.agent_id)
    print("  ecr_uri:", launch_result.ecr_uri)

    end_status = {"READY", "CREATE_FAILED", "DELETE_FAILED", "UPDATE_FAILED"}
    while True:
        status_response: Any = runtime.status()
        status = status_response.endpoint.get("status")
        print("Status:", status)
        if status in end_status:
            break
        time.sleep(10)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
