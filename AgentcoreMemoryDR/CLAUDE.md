# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A proof-of-concept for multi-region disaster recovery of LangGraph agent conversation state using AWS Bedrock AgentCore Memory. The agent writes checkpoints to two AWS regions simultaneously so that if one region fails, conversation history is preserved in the other.

## Architecture

The system deploys the same agent to two AWS regions (us-west-2 and eu-west-1) with cross-linked memory:

- **`MultiRegionAgentCoreMemorySaver`** (`multi_region_memory_saver.py`) is the core component. It wraps `AgentCoreMemorySaver` from `langgraph-checkpoint-aws` and implements the LangGraph `BaseCheckpointSaver` interface. Reads go to primary region only; writes go to both regions (both must succeed).
- **`agent.py`** creates a LangGraph ReAct agent wired to the multi-region checkpointer. It selects the Bedrock cross-region inference profile prefix (`us.`/`eu.`/`apac.`) based on the primary region.
- **`agent_runtime.py`** is the `BedrockAgentCoreApp` entrypoint that gets containerized and deployed to AgentCore.
- **`enable_memory_replication.py`** is a one-time setup script run after deploying to both regions. It reads each region's `PRIMARY_MEMORY_ID` and sets the other region's `SECONDARY_REGION`/`SECONDARY_MEMORY_ID` env vars on the deployed agent runtime.

## Infrastructure (Terraform)

Terraform uses **workspaces** to deploy the same config (`terraform/main.tf`) to each region. Each workspace provisions: ECR repo, AgentCore Memory, IAM role, and AgentCore agent runtime.

```bash
# Deploy to a region
cd terraform
terraform workspace new us-west-2    # or select existing
terraform apply -var="aws_region=us-west-2"

terraform workspace new eu-west-1
terraform apply -var="aws_region=eu-west-1"

# After both regions are up, cross-link memory:
python enable_memory_replication.py
```

## Environment Variables (required at runtime)

- `PRIMARY_REGION` / `SECONDARY_REGION` — AWS region names
- `PRIMARY_MEMORY_ID` / `SECONDARY_MEMORY_ID` — AgentCore Memory IDs

These are set automatically by Terraform (`PRIMARY_*`) and by `enable_memory_replication.py` (`SECONDARY_*`).

## Testing

Two test files with different scopes:

```bash
# Local tests — creates agent in-process, talks directly to AWS memory APIs
# Requires valid AWS credentials and all 4 env vars set
pytest test_agent_local.py -v

# AWS tests — invokes the deployed AgentCore runtime over the wire
# Requires deployed agents in both regions; uses a shared thread ID
# Tests are ordered (store → recall → verify) via pytest-ordering
pytest test_agent_aws.py -v
```

`test_agent_aws.py` imports helpers from `test_agent_local.py` (aliased as `test_agent` in its import).

## CLI

```bash
python agent_cli.py --region us-west-2 --actor-id my-user
```

Interactive REPL that discovers the deployed agent runtime by name (`dr_poc_agent`) and opens a session.
