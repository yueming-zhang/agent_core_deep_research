import boto3
import json
import uuid
import pytest
from datetime import datetime
from test_agent import get_memory_id, get_latest_memory_events, events_contain_text

REGIONS = ["us-west-2", "eu-west-1"]
AGENT_NAME = "dr_poc_agent"
MEMORY_NAME = "dr_poc_memory"
THREAD_ID = "persistence-test-fixed"

session_id_store = {}
memorable_code = {}

def get_agent_runtime_arn(region):
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    paginator = client.get_paginator("list_agent_runtimes")
    for page in paginator.paginate():
        for runtime in page.get("agentRuntimes", []):
            if runtime["agentRuntimeName"] == AGENT_NAME:
                return runtime["agentRuntimeArn"]
    return None

def stop_session(arn, session_id, region):
    client = boto3.client("bedrock-agentcore", region_name=region)
    client.stop_runtime_session(agentRuntimeArn=arn, runtimeSessionId=session_id, qualifier="DEFAULT")

def invoke_agent(arn, prompt, session_id, region):
    client = boto3.client("bedrock-agentcore", region_name=region)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        qualifier="DEFAULT",
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt, "thread_id": THREAD_ID})
    )
    return "".join(event.decode("utf-8") for event in response.get("response", []))

@pytest.mark.parametrize("region", REGIONS)
@pytest.mark.order(1)
def test_store(region):
    global session_id_store, memorable_code
    memorable_code[region] = datetime.now().strftime(f"memorable-{region}-%Y%m%d-%H%M%S")
    arn = get_agent_runtime_arn(region)
    session_id_store[region] = f"session-{uuid.uuid4()}"
    response = invoke_agent(arn, f"My memorable code is {memorable_code[region]}. Remember this.", session_id_store[region], region)
    assert response, f"No response in {region}"
    stop_session(arn, session_id_store[region], region)

@pytest.mark.parametrize("region", REGIONS)
@pytest.mark.order(2)
def test_recall(region):
    arn = get_agent_runtime_arn(region)
    new_session_id = f"session-{uuid.uuid4()}"
    response = invoke_agent(arn, "What is my memorable code?", new_session_id, region)
    assert memorable_code[region] in response, f"memorable code not recalled in {region}"
    stop_session(arn, new_session_id, region)

@pytest.mark.parametrize("region", REGIONS)
@pytest.mark.order(3)
def test_verify_memory_storage(region):
    memory_id = get_memory_id(region)
    events = get_latest_memory_events(memory_id, THREAD_ID, "agent-1", region)
    assert events_contain_text(events, memorable_code[region]), f"memorable code {memorable_code[region]} not found in memory ({region})"