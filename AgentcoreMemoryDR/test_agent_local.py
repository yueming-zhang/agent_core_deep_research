import pytest, os, boto3, uuid, json, base64, msgpack
from agent import create_agent, invoke_agent

REGIONS = ["us-west-2", "eu-west-1"]
MEMORY_NAME = "dr_poc_memory"
DEFAULT_ACTOR = "test_actor"

def get_memory_id(region):
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    response = client.list_memories()
    for memory in response.get("memories", []):
        if memory.get("id", "").startswith(MEMORY_NAME):
            return memory.get("id")
    return None

def get_secondary_region(primary_region: str) -> str:
    """Get the secondary region from the DR pair."""
    other_regions = set(REGIONS) - {primary_region}
    return other_regions.pop()

def get_latest_memory_events(memory_id, session_id, actor_id, region):
    client = boto3.client("bedrock-agentcore", region_name=region)
    response = client.list_events(memoryId=memory_id, sessionId=session_id, actorId=actor_id, includePayloads=True, maxResults=10)
    return response.get("events", [])

def events_contain_text(events, text):
    """Check if any event payload blob contains the given text (decodes msgpack if needed)."""
    for event in events:
        for payload in event.get("payload", []):
            blob = payload.get("blob", "")
            if text.lower() in blob.lower():
                return True
            try:
                data = json.loads(blob)
                if "value" in data and isinstance(data["value"], dict) and "data" in data["value"]:
                    decoded = msgpack.unpackb(base64.b64decode(data["value"]["data"]), raw=False)
                    if text.lower() in str(decoded).lower():
                        return True
            except Exception:
                pass
    return False

@pytest.fixture(params=REGIONS)
def agent(request):
    primary_region = request.param
    secondary_region = get_secondary_region(primary_region)
    
    primary_memory_id = get_memory_id(primary_region)
    secondary_memory_id = get_memory_id(secondary_region)
    
    if not primary_memory_id:
        pytest.fail(f"Memory '{MEMORY_NAME}' not found in primary region {primary_region}")
    if not secondary_memory_id:
        pytest.fail(f"Memory '{MEMORY_NAME}' not found in secondary region {secondary_region}")
    
    os.environ['PRIMARY_REGION'] = primary_region
    os.environ['SECONDARY_REGION'] = secondary_region
    os.environ['PRIMARY_MEMORY_ID'] = primary_memory_id
    os.environ['SECONDARY_MEMORY_ID'] = secondary_memory_id
    
    return create_agent(), primary_region

def test_agent_basic_response(agent):
    agent_instance, region = agent
    response = invoke_agent(agent_instance, "Hello, my name is Alice", thread_id=f"test-basic-{uuid.uuid4().hex[:8]}", actor_id=DEFAULT_ACTOR)
    assert response is not None and "messages" in response and len(response["messages"]) > 0, f"Failed in {region}"

def test_agent_memory_persistence(agent):
    agent_instance, region = agent
    session_id = f"test-memory-{uuid.uuid4().hex[:8]}"
    invoke_agent(agent_instance, "I like pizza", thread_id=session_id, actor_id=DEFAULT_ACTOR)

    # verify the message is in memory
    events = get_latest_memory_events(os.environ['PRIMARY_MEMORY_ID'], session_id, actor_id=DEFAULT_ACTOR, region=region)
    assert events_contain_text(events, "pizza"), f"'I like pizza' not found in memory ({region})"

    # verify by calling it again
    response = invoke_agent(agent_instance, "What do I like?", thread_id=session_id, actor_id=DEFAULT_ACTOR)
    assert "pizza" in response["messages"][-1].content.lower(), f"Memory recall failed in {region}"

def test_agent_different_sessions(agent):
    agent_instance, region = agent
    session1, session2 = f"test-diff-{uuid.uuid4().hex[:8]}", f"test-diff-{uuid.uuid4().hex[:8]}"
    invoke_agent(agent_instance, "My favorite color is blue", thread_id=session1, actor_id=DEFAULT_ACTOR)
    response = invoke_agent(agent_instance, "What is my favorite color?", thread_id=session2, actor_id=DEFAULT_ACTOR)
    assert response is not None and "messages" in response, f"Failed in {region}"


def test_recall_2nd_region(agent):
    """Verify the secret code stored via primary region is also available in the secondary region."""
    agent_instance, primary_region = agent
    secondary_region = os.environ['SECONDARY_REGION']
    session_id = f"test-2nd-recall-{uuid.uuid4().hex[:8]}"
    secret_code = f"SECRET-{uuid.uuid4().hex[:6].upper()}"
    
    # Store secret code via the agent (writes to both regions)
    invoke_agent(agent_instance, f"Remember this secret code: {secret_code}", thread_id=session_id, actor_id=DEFAULT_ACTOR)
    
    # Verify the secret code is in the secondary region's memory
    secondary_memory_id = os.environ['SECONDARY_MEMORY_ID']
    
    events = get_latest_memory_events(secondary_memory_id, session_id, actor_id=DEFAULT_ACTOR, region=secondary_region)
    assert events_contain_text(events, secret_code), f"Secret code '{secret_code}' not found in secondary region ({secondary_region})"

def test_verify_2nd_region_memory_storage(agent):
    """Verify information stored is available in the secondary region's memory storage."""
    agent_instance, primary_region = agent
    secondary_region = os.environ['SECONDARY_REGION']
    session_id = f"test-2nd-storage-{uuid.uuid4().hex[:8]}"
    unique_info = f"UNIQUE-INFO-{uuid.uuid4().hex[:8]}"
    
    # Store information via the agent (writes to both regions)
    invoke_agent(agent_instance, f"Please remember this important information: {unique_info}", thread_id=session_id, actor_id=DEFAULT_ACTOR)
    
    # Get memory IDs for both regions
    primary_memory_id = os.environ['PRIMARY_MEMORY_ID']
    secondary_memory_id = os.environ['SECONDARY_MEMORY_ID']
    
    # Verify information exists in primary region
    primary_events = get_latest_memory_events(primary_memory_id, session_id, actor_id=DEFAULT_ACTOR, region=primary_region)
    assert events_contain_text(primary_events, unique_info), f"Info not found in primary region ({primary_region})"
    
    # Verify information exists in secondary region
    secondary_events = get_latest_memory_events(secondary_memory_id, session_id, actor_id=DEFAULT_ACTOR, region=secondary_region)
    assert events_contain_text(secondary_events, unique_info), f"Info not found in secondary region ({secondary_region})"
    
    # Verify both regions have the same number of events for this session
    assert len(primary_events) == len(secondary_events), \
        f"Event count mismatch: primary={len(primary_events)}, secondary={len(secondary_events)}"