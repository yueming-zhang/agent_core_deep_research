from bedrock_agentcore import BedrockAgentCoreApp
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage, AIMessage
from langchain_aws import ChatBedrock

app = BedrockAgentCoreApp()

# Create a simple LangGraph agent
def chatbot(state: MessagesState):
    """Simple chatbot node that responds to messages."""
    llm = ChatBedrock(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0")
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

# Build the graph
builder = StateGraph(MessagesState)
builder.add_node("chatbot", chatbot)
builder.add_edge(START, "chatbot")
builder.add_edge("chatbot", END)
graph = builder.compile()


@app.entrypoint
def invoke(payload):
    """Your AI agent function"""
    user_message = payload.get("prompt", "Hello! How can I help you today?")
    
    response = graph.invoke(
        {"messages": [HumanMessage(content=user_message)]}
    )
    
    # Extract the last AI message
    last_message = response["messages"][-1]
    return {"result": last_message.content}


if __name__ == "__main__":
    app.run()



# To test
# 1. python my_langgraph_agent.py
# 2. go to second terminal window run: 
#    curl -X POST http://localhost:8080/invocations -H "Content-Type: application/json" -d '{"prompt": "Hello!"}'
