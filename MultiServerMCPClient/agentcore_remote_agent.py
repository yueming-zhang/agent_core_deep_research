"""AgentCore Runtime entrypoint for the LangGraph agent that uses MultiServerMCPClient.

This deploys an HTTP AgentCore runtime that, on each invocation:
1) Connects to a remote MCP server (typically another AgentCore runtime) using SigV4.
2) Loads the MCP tools.
3) Runs a LangGraph agent that can call those tools.

This file intentionally does not read configuration from environment variables.
If you need to change the target MCP server or model, edit the constants below.

Payload format (HTTP protocol):
  {"prompt": "..."}

Response:
  {"result": "..."}
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
from bedrock_agentcore import BedrockAgentCoreApp
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_aws import ChatBedrock
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, MessagesState, StateGraph
from opentelemetry import trace

# Ensure repo root + this folder are on sys.path (for local runs and runtime builds).
_this_dir = Path(__file__).resolve().parent
_repo_root = _this_dir.parent
for _p in (str(_repo_root), str(_this_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from streamable_http_sigv4 import SigV4HTTPXAuth  # noqa: E402


REGION = "us-west-2"
MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
SERVICE_NAME = "bedrock-agentcore"

app = BedrockAgentCoreApp()


def _create_sigv4_auth(*, region: str) -> SigV4HTTPXAuth:
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise RuntimeError("No AWS credentials available for SigV4 signing.")
    return SigV4HTTPXAuth(
        credentials=credentials,
        service=SERVICE_NAME,
        region=region,
    )


def _create_agent(tools, *, region: str):
    llm = ChatBedrock(
        model_id=MODEL_ID,
        region_name=region,
    )
    llm_with_tools = llm.bind_tools(tools)
    tools_by_name = {tool.name: tool for tool in tools}

    async def agent_node(state: MessagesState):
        messages = state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        new_messages = [response]

        # Guard against runaway tool loops.
        for _ in range(12):
            if not response.tool_calls:
                break

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args") or {}
                tool_id = tool_call["id"]

                tool = tools_by_name.get(tool_name)
                if tool is None:
                    result = f"Tool {tool_name} not found"
                else:
                    result = await tool.ainvoke(tool_args)

                new_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

            response = await llm_with_tools.ainvoke(messages + new_messages)
            new_messages.append(response)

        return {"messages": new_messages}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()


_init_lock = asyncio.Lock()
_cached = {
    "client": None,
    "tools": None,
    "agent": None,
    "region": None,
}


async def _get_or_init() -> tuple[Any, Any]:
    async with _init_lock:
        if _cached.get("agent") is not None and _cached.get("region") is not None:
            return _cached["agent"], _cached["region"]

        region = REGION
        AGENTCORE_MCP_URL = "https://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-west-2%3A482387069690%3Aruntime%2Fmcp_server_iam-rgCYhOFeIC/invocations?qualifier=DEFAULT"

        client = MultiServerMCPClient(
            {
                "agentcore": {
                    "transport": "streamable_http",
                    "url": AGENTCORE_MCP_URL,
                    "auth": _create_sigv4_auth(region=region),
                    "terminate_on_close": False,
                }
            }
        )

        tools = await client.get_tools()
        agent = _create_agent(tools, region=region)

        _cached["client"] = client
        _cached["tools"] = tools
        _cached["agent"] = agent
        _cached["region"] = region
        return agent, region


@app.entrypoint
async def invoke(payload: dict[str, Any]):

    tracer = trace.get_tracer("mz_agentcore_runtime", "1.0.0")
    with tracer.start_as_current_span("mz_agentcore_runtime_invoke") as span:
        span.add_event("mz_invoke_start", {"payload": str(payload)})
        prompt = payload.get("prompt", "")
        if not isinstance(prompt, str):
            prompt = str(prompt)

        agent, _region = await _get_or_init()
        result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        messages = result.get("messages") or []
        final = messages[-1].content if messages else ""
        span.add_event("mz_invoke_end", {"result": str(final)})
        
        return {"result": final}

if __name__ == "__main__":
    app.run()
