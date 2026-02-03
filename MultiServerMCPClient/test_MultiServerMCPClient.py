"""
LangGraph agent using MultiServerMCPClient with AWS SigV4 authentication.
"""

import asyncio
import boto3
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_aws import ChatBedrock
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import StateGraph, MessagesState, START, END

# Import the SigV4 auth class from the existing module
from streamable_http_sigv4 import SigV4HTTPXAuth


# Config
AGENTCORE_MCP_URL = "https://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-west-2%3A482387069690%3Aruntime%2Fmcp_server_iam-rgCYhOFeIC/invocations?qualifier=DEFAULT"
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


async def main():
    print("=" * 60)
    print("LangGraph Agent with MultiServerMCPClient + SigV4 Auth")
    print("=" * 60)
    
    # Create MultiServerMCPClient with SigV4 auth
    client = MultiServerMCPClient({
        "agentcore": {
            "transport": "streamable_http",
            "url": AGENTCORE_MCP_URL,
            "auth": create_sigv4_auth(),  # Pass SigV4 auth handler
            "terminate_on_close": False,
        },
        # Add other MCP servers here:
        # "weather": {
        #     "transport": "http",
        #     "url": "http://localhost:8000/mcp",
        # },ß
    })
    
    # Reuse a single MCP session for tool loading + all tool calls
    async with client.session("agentcore") as session:
        tools = await load_mcp_tools(
            session,
            callbacks=client.callbacks,
            tool_interceptors=client.tool_interceptors,
            server_name="agentcore",
        )
        print(f"\n📋 Loaded {len(tools)} tools: {[t.name for t in tools]}")

        agent = create_agent(tools)

        prompts = [
            "What is 15 + 27?",
            "Multiply 6 and 8",
            "Say hello to Bob",
        ]

        for prompt in prompts:
            print(f"\n{'='*60}")
            print(f"🧑 User: {prompt}")
            print("-" * 40)

            result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
            final_response = result["messages"][-1].content
            print(f"🤖 Agent: {final_response}")


if __name__ == "__main__":
    asyncio.run(main())
