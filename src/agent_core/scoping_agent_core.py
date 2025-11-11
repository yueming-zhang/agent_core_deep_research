from pathlib import Path
import sys
import dotenv
from langchain_core.messages import HumanMessage
from bedrock_agentcore import BedrockAgentCoreApp
from langgraph.checkpoint.memory import InMemorySaver
dotenv.load_dotenv()

sys.path.append(str(Path(__file__).parents[1]))
from deep_research.research_agent_scope import deep_researcher_builder


app = BedrockAgentCoreApp()
checkpointer = InMemorySaver()
agent = deep_researcher_builder.compile(checkpointer=checkpointer)



@app.entrypoint
def langgraph_bedrock(payload):
    user_input = payload.get("prompt")
    thread_id = payload.get("thread_id", "default")
    
    response = agent.invoke(
        {"messages": [HumanMessage(content=user_input)]},
        config={"configurable": {"thread_id": thread_id}}
    )
    return response

if __name__ == "__main__":
    app.run()