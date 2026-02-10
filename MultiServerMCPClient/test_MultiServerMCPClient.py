"""
LangGraph agent using MultiServerMCPClient with AWS SigV4 authentication.
"""

import asyncio
import datetime
import sys
import uuid
import boto3
from contextlib import AsyncExitStack
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_aws import ChatBedrock
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import StateGraph, MessagesState, START, END

# Import the SigV4 auth class from the existing module
from streamable_http_sigv4 import SigV4HTTPXAuth


region = "us-west-2"
ssm_client = boto3.client("ssm", region_name=region)
agent_arn_response = ssm_client.get_parameter(Name="/mcp_server/runtime_iam/agent_arn")
agent_arn = agent_arn_response["Parameter"]["Value"]
encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
AGENTCORE_MCP_URL = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

REGION = "us-west-2"


def create_sigv4_auth():
    """Create SigV4 auth handler for AWS-authenticated MCP servers."""
    credentials = boto3.Session().get_credentials()
    return SigV4HTTPXAuth(
        credentials=credentials,
        service="bedrock-agentcore",
        region=REGION,
    )


def create_agent(tools):
    """Create a LangGraph agent with one node that handles tool calls."""
    llm = ChatBedrock(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        region_name=REGION,
    )
    llm_with_tools = llm.bind_tools(tools)
    tools_by_name = {tool.name: tool for tool in tools}
    
    async def agent_node(state: MessagesState):
        """Single node that calls LLM and executes tools."""
        messages = state["messages"]
        
        # Call LLM
        response = await llm_with_tools.ainvoke(messages)
        new_messages = [response]
        
        # If LLM wants to use tools, execute them
        while response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                print(f"   🔧 Calling {tool_name}({tool_args})")
                
                # Execute tool
                tool = tools_by_name.get(tool_name)
                if tool:
                    result = await tool.ainvoke(tool_args)
                    print(f"   ✅ Result: {result}")
                else:
                    result = f"Tool {tool_name} not found"
                
                new_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))
            
            # Call LLM again with tool results
            response = await llm_with_tools.ainvoke(messages + new_messages)
            new_messages.append(response)
        
        return {"messages": new_messages}
    
    # Build graph with single node
    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    
    return graph.compile()


async def run_agent_with_prompts_single_session(client: MultiServerMCPClient, prompts: list[str]):
    async with client.session(server_name="agentcore1") as session:
        tools = await load_mcp_tools(
            session,
            callbacks=client.callbacks,
            tool_interceptors=client.tool_interceptors,
            server_name="agentcore1",
        )
        print(f"\n📋 Loaded {len(tools)} tools: {[t.name for t in tools]}")

        agent = create_agent(tools)

        for prompt in prompts:
            print(f"\n{'='*60}")
            print(f"🧑 User: {prompt}")
            print("-" * 40)

            result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
            final_response = result["messages"][-1].content
            print(f"🤖 Agent: {final_response}")

async def run_agent_without_session(client: MultiServerMCPClient, prompts: list[str]):

    tools = await client.get_tools()
    print(f"\n📋 Loaded {len(tools)} tools: {[t.name for t in tools]}")

    agent = create_agent(tools)

    for prompt in prompts:
        print(f"\n{'='*60}")
        print(f"🧑 User: {prompt}")
        print("-" * 40)

        result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        final_response = result["messages"][-1].content
        print(f"🤖 Agent: {final_response}")

async def run_agent_with_prompts_multi_server(client: MultiServerMCPClient, prompts: list[str]):
    """
    Run agent with explicit session management for all configured servers.
    This is the most efficient approach per session_behavior_analysis.md:
    - Uses explicit sessions (not headers)
    - Minimizes invocations (~6 vs ~15)
    - All servers maintain their sessions throughout execution
    """
    server_names = list(client.connections.keys())
    print(f"\n🌐 Opening explicit sessions for {len(server_names)} servers: {server_names}")
    
    # Use AsyncExitStack to manage multiple session contexts simultaneously
    async with AsyncExitStack() as stack:
        all_tools = []
        
        # Open an explicit session for each server - most efficient approach
        for server_name in server_names:
            print(f"   🔌 Connecting to '{server_name}'...")
            session = await stack.enter_async_context(client.session(server_name=server_name))
            tools = await load_mcp_tools(
                session,
                callbacks=client.callbacks,
                tool_interceptors=client.tool_interceptors,
                server_name=server_name,
            )
            print(f"   ✅ Loaded {len(tools)} tools from '{server_name}': {[t.name for t in tools]}")
            all_tools.extend(tools)
        
        print(f"\n📋 Total tools loaded: {len(all_tools)}")
        print("📌 All sessions are now active and will remain open for all prompts")

        agent = create_agent(all_tools)

        # Execute all prompts with sessions maintained throughout
        for prompt in prompts:
            print(f"\n{'='*60}")
            print(f"🧑 User: {prompt}")
            print("-" * 40)

            result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
            final_response = result["messages"][-1].content
            print(f"🤖 Agent: {final_response}")
        
        print(f"\n🏁 All prompts completed. Sessions will now close.")

async def main():
    # Using explicit session management - no need for session headers
    # This approach gives the best performance per session_behavior_analysis.md
    client = MultiServerMCPClient({
        "agentcore1": {
            "transport": "streamable_http",
            "url": AGENTCORE_MCP_URL,
            "auth": create_sigv4_auth(),
            "terminate_on_close": False,
            # Note: No Mcp-Session-Id header needed with explicit session management
        },
        # Add other MCP servers here:
        # "weather": {
        #     "transport": "http",
        #     "url": "http://localhost:8000/mcp",
        # },
    })
    
    prompts = [
        "What is 15 + 27?",
        "Multiply 6 and 8",
        "Say hello to Bob",
    ]
    
    # Use multi-server with explicit session management (most efficient)
    await run_agent_with_prompts_multi_server(client, prompts)
    
    # Alternative approaches for comparison:
    # await run_agent_with_prompts_single_session(client, prompts)  # Single server only
    # await run_agent_without_session(client, prompts)  # Less efficient: ~15 invocations


if __name__ == "__main__":
    asyncio.run(main())
