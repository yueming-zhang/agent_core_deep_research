from pathlib import Path
import sys
import boto3
from langchain_core.messages import HumanMessage
from bedrock_agentcore import BedrockAgentCoreApp
from langgraph.checkpoint.memory import InMemorySaver
import os
import dotenv


def load_env():
    env_path = Path(__file__).parents[1] / '.env'
    
    if env_path.exists():
        print(f"Loading environment from .env file: {env_path}")
        dotenv.load_dotenv(env_path)
    else:
        print(f".env file not found, loading from AWS SSM Parameter Store")
        keys = ["ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT",
                "LANGSMITH_TRACING", "OPENAI_API_KEY", "TAVILY_API_KEY"]
        
        client = boto3.client('ssm', region_name='us-west-2')
        
        for key in keys:
            key_path = f'/deep_research_scoping_agent/{key}'
            response = client.get_parameter(Name=key_path, WithDecryption=True)
            os.environ[key] = response['Parameter']['Value']
            print(f"{key} loaded from SSM")

load_env()

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


''' 
To run the app as a server, use the command:
    cd src/agent_core
    python scoping_agent_core.py

To test: 
    curl -X POST http://localhost:8080/invocations   -H "Content-Type: application/json"   -d '{"prompt": "I want to research the best coffee shops in San Francisco.", "thread_id": "test-thread-2"}'   


To run the app inside the docker container, use:
    docker build -f src/Dockerfile -t agent-core .
    
    start the container session 1:
        docker run -it -p 8080:8080 agent-core /bin/bash
        docker run -it 482387069690.dkr.ecr.us-west-2.amazonaws.com/deep_research_scoping_agent /bin/bash
                       482387069690.dkr.ecr.us-west-2.amazonaws.com/deep_research_scoping_agent:latest
        python src/agent_core/scoping_agent_core.py

    start another terminal session 2:
        docker ps
        docker exec -it <container_id> /bin/bash
        curl -X POST http://localhost:8080/invocations \
            -H "Content-Type: application/json" \
            -d '{"prompt": "I want to research the best coffee shops in San Francisco.", "thread_id": "test-thread-2"}'

To test inside the docker container, use the same curl command as above.    

'''