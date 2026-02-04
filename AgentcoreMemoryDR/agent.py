import os
from langchain_aws import ChatBedrock
from langchain.agents import create_agent as create_react_agent
from multi_region_memory_saver import MultiRegionAgentCoreMemorySaver


# Cross-region inference profiles by region prefix
# US regions use "us." prefix, EU regions use "eu." prefix
def get_model_id(region):
    if region.startswith("us-"):
        return "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    elif region.startswith("eu-"):
        return "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    elif region.startswith("ap-"):
        return "apac.anthropic.claude-haiku-4-5-20251001-v1:0"
    else:
        raise ValueError(f"Unsupported region: {region}")


def create_agent():
    primary_region = os.environ["PRIMARY_REGION"]
    secondary_region = os.environ["SECONDARY_REGION"]
    primary_memory_id = os.environ["PRIMARY_MEMORY_ID"]
    secondary_memory_id = os.environ["SECONDARY_MEMORY_ID"]
    
    checkpointer = MultiRegionAgentCoreMemorySaver(
        primary_region=primary_region,
        secondary_region=secondary_region,
        primary_memory_id=primary_memory_id,
        secondary_memory_id=secondary_memory_id,
    )
    
    model_id = get_model_id(primary_region)
    llm = ChatBedrock(model_id=model_id, region_name=primary_region)
    return create_react_agent(model=llm, tools=[], checkpointer=checkpointer)

def invoke_agent(graph, message: str, thread_id: str, actor_id: str):
    config = {"configurable": {"thread_id": thread_id, "actor_id": actor_id}}
    return graph.invoke({"messages": [("human", message)]}, config=config)