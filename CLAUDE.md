# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP server and client toolkit for hosting tools on AWS Bedrock AgentCore Runtime, with LangGraph agent integration. The primary working directory is `MultiServerMCPClient/`.

## Commands

```bash
# Install dependencies (from repo root)
uv sync

# Run the MCP server locally (starts on 0.0.0.0:8000/mcp)
cd MultiServerMCPClient && python mcp_server.py

# Test local MCP connectivity (server must be running)
cd MultiServerMCPClient && python mcp_client.py

# Test remote AgentCore MCP server (requires AWS credentials + SSM param)
cd MultiServerMCPClient && python mcp_client_remote.py

# Invoke remote MCP tools directly
cd MultiServerMCPClient && python invoke_mcp_tools.py

# Parallel MCP tool invocations
cd MultiServerMCPClient && python invoke_mcp_parallel.py --operation add_numbers --thread-count 5

# Run LangGraph agent with MCP tools (requires remote MCP server)
cd MultiServerMCPClient && python test_MultiServerMCPClient.py

# Deploy agent to AgentCore (creates or upgrades runtime)
cd MultiServerMCPClient && python deploy_agent.py

# Verify deployed runtime
cd MultiServerMCPClient && python test_remote_agent.py

# Lint (from repo root)
uv run ruff check src/
```

## Architecture

### MCP Server (`mcp_server.py`)

FastMCP server with `stateless_http=True` transport, providing three tools: `add_numbers` (sync), `multiply_numbers` (async), `greet_user` (sync). All tools include OpenTelemetry tracing spans. Runs on port 8000 at `/mcp`.

### SigV4 Auth (`streamable_http_sigv4.py`)

Custom MCP transport layer for AWS IAM authentication. Two key classes:
- `SigV4HTTPXAuth`: HTTPX auth handler that signs requests with SigV4. Strips the `connection` header before signing to avoid signature mismatch.
- `StreamableHTTPTransportWithSigV4`: Extends MCP's `StreamableHTTPTransport`, passing `SigV4HTTPXAuth` as the `auth` parameter.
- `streamablehttp_client_with_sigv4()`: Async context manager wrapping the standard `streamablehttp_client` with SigV4 auth. Drop-in replacement.

### Tool Proxy Cache (`tool_proxy.py`)

`ToolProxyLayer` wraps LangChain `StructuredTool` objects with SHA256-based caching. Replaces each tool's `coroutine` with a cached version that checks a hash of `(tool_name, kwargs)` before executing. Tools in `no_cache_tools` bypass the cache.

### LangGraph Agent (`test_MultiServerMCPClient.py`)

LangGraph agent using `MultiServerMCPClient` to connect to remote AgentCore MCP servers. Three execution modes with different session/invocation tradeoffs:

| Mode | Function | Sessions | Invocations | Notes |
|------|----------|----------|-------------|-------|
| Explicit session | `run_agent_with_prompts_single_session()` | 2 | ~6 | Most efficient; uses `client.session()` |
| Multi-server session | `run_agent_with_prompts_multi_server()` | N | ~6 | Uses `AsyncExitStack` for multiple servers |
| No session | `run_agent_without_session()` | 4 | ~15 | 2.5x overhead from repeated init/teardown |

The agent node pattern: bind tools to `ChatBedrock` (Claude 3.5 Sonnet), loop calling LLM → execute tool calls → feed results back until no more tool calls.

### Remote Agent Runtime (`agentcore_remote_agent.py`)

`BedrockAgentCoreApp` entrypoint for deploying the LangGraph agent on AgentCore. Lazily initializes `MultiServerMCPClient` + agent with `asyncio.Lock()` so the MCP connection persists across invocations (warm start). Payload: `{"prompt": "..."}` → Response: `{"result": "..."}`.

### Deployment (`deploy_agent.py`)

Uses `bedrock_agentcore_starter_toolkit.Runtime` to configure and launch. Checks if agent exists by name → creates or upgrades. Polls status until terminal state. References `requirements.runtime.txt` and `agentcore_remote_agent.py` as build inputs.

### MCP Client Variants

- `mcp_client.py` / `my_mcp_client.py`: Minimal clients for local server testing (the latter uses `timedelta` for timeout)
- `mcp_client_remote.py`: Connects to remote AgentCore MCP via SigV4, lists tools with pagination support via `get_full_tools_list()`
- `invoke_mcp_tools.py`: Directly calls individual tools on remote server (no LLM)
- `invoke_mcp_parallel.py`: Benchmarks parallel `session.call_tool()` via `asyncio.gather()` on a single session

## Key Patterns

- MCP server ARN is stored in AWS SSM at `/mcp_server/runtime_iam/agent_arn` and URL-encoded for the AgentCore invocations endpoint
- AgentCore MCP URL format: `https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT`
- Server must use `stateless_http=True` because AgentCore provides session isolation and injects `Mcp-Session-Id` headers
- Explicit session management (`client.session()`) is strongly preferred over implicit — see `session_behavior_analysis.md` for the 2.5x invocation overhead analysis
- `requirements.runtime.txt` is separate from the repo's main `pyproject.toml` — it defines the minimal deps for the AgentCore container image
