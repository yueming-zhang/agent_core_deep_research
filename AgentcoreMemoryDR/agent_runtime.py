from agent import create_agent
from langchain_core.messages import HumanMessage
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()
agent = create_agent()

@app.entrypoint
def invoke(payload):
    prompt = payload.get("prompt")
    thread_id = payload.get("thread_id", "default")
    actor_id = payload.get("actor_id", "agent-1")
    
    config = {"configurable": {"thread_id": thread_id, "actor_id": actor_id}}
    response = agent.invoke({"messages": [HumanMessage(content=prompt)]}, config=config)
    return response["messages"][-1].content

if __name__ == "__main__":
    app.run()