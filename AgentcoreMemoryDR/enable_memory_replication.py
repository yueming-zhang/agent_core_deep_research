#!/usr/bin/env python3
"""
Enable memory replication between DR regions for dr_poc_agent.

This script updates the environment variables in both regions so each agent
knows about the other region's memory ID for cross-region replication.

- us-west-2's SECONDARY_MEMORY_ID = eu-west-1's PRIMARY_MEMORY_ID
- us-west-2's SECONDARY_REGION = eu-west-1
- eu-west-1's SECONDARY_MEMORY_ID = us-west-2's PRIMARY_MEMORY_ID
- eu-west-1's SECONDARY_REGION = us-west-2
"""

import boto3

AGENT_NAME = "dr_poc_agent"
REGION_US = "us-west-2"
REGION_EU = "eu-west-1"


def get_agent_runtime_id(region: str, agent_name: str) -> str:
    """Get agent runtime ID by name."""
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    paginator = client.get_paginator("list_agent_runtimes")
    for page in paginator.paginate():
        for runtime in page["agentRuntimes"]:
            if runtime["agentRuntimeName"] == agent_name:
                return runtime["agentRuntimeId"]
    raise ValueError(f"Agent runtime '{agent_name}' not found in {region}")


def get_agent_runtime(region: str, runtime_id: str) -> dict:
    """Get agent runtime details including environment variables."""
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    response = client.get_agent_runtime(agentRuntimeId=runtime_id)
    return response


def update_agent_runtime_env(region: str, runtime_id: str, env_updates: dict) -> None:
    """Update agent runtime environment variables."""
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    
    # Get current runtime config
    runtime = get_agent_runtime(region, runtime_id)
    current_env = runtime.get("environmentVariables", {})
    
    # Merge updates
    updated_env = {**current_env, **env_updates}
    
    # Update the agent runtime with all required fields
    client.update_agent_runtime(
        agentRuntimeId=runtime_id,
        roleArn=runtime["roleArn"],
        networkConfiguration=runtime["networkConfiguration"],
        agentRuntimeArtifact=runtime["agentRuntimeArtifact"],
        environmentVariables=updated_env,
    )
    print(f"Updated {AGENT_NAME} in {region} with: {env_updates}")


def main():
    print("Fetching agent runtime configurations...")
    
    # Get runtime IDs
    us_runtime_id = get_agent_runtime_id(REGION_US, AGENT_NAME)
    eu_runtime_id = get_agent_runtime_id(REGION_EU, AGENT_NAME)
    
    print(f"{REGION_US} runtime ID: {us_runtime_id}")
    print(f"{REGION_EU} runtime ID: {eu_runtime_id}")
    
    # Get current configs from both regions
    us_runtime = get_agent_runtime(REGION_US, us_runtime_id)
    eu_runtime = get_agent_runtime(REGION_EU, eu_runtime_id)
    
    us_env = us_runtime.get("environmentVariables", {})
    eu_env = eu_runtime.get("environmentVariables", {})
    
    us_primary_memory_id = us_env.get("PRIMARY_MEMORY_ID")
    eu_primary_memory_id = eu_env.get("PRIMARY_MEMORY_ID")
    
    if not us_primary_memory_id:
        raise ValueError(f"PRIMARY_MEMORY_ID not found in {REGION_US}")
    if not eu_primary_memory_id:
        raise ValueError(f"PRIMARY_MEMORY_ID not found in {REGION_EU}")
    
    print(f"\n{REGION_US} PRIMARY_MEMORY_ID: {us_primary_memory_id}")
    print(f"{REGION_EU} PRIMARY_MEMORY_ID: {eu_primary_memory_id}")
    
    # Update us-west-2: set secondary to eu-west-1's primary
    print(f"\nUpdating {REGION_US}...")
    update_agent_runtime_env(REGION_US, us_runtime_id, {
        "SECONDARY_REGION": REGION_EU,
        "SECONDARY_MEMORY_ID": eu_primary_memory_id,
    })
    
    # Update eu-west-1: set secondary to us-west-2's primary
    print(f"\nUpdating {REGION_EU}...")
    update_agent_runtime_env(REGION_EU, eu_runtime_id, {
        "SECONDARY_REGION": REGION_US,
        "SECONDARY_MEMORY_ID": us_primary_memory_id,
    })
    
    print("\nMemory replication enabled successfully!")


if __name__ == "__main__":
    main()