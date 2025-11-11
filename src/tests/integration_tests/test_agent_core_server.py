import pytest
import subprocess
import time
import requests
import signal
import os
from pathlib import Path


@pytest.fixture
def agent_server():
    """Start the scoping agent core server as a subprocess and clean up after test."""
    # Path to the scoping_agent_core.py file
    agent_path = Path(__file__).parents[2] / "agent_core" / "scoping_agent_core.py"
    
    # Start the server process
    process = subprocess.Popen(
        ["python", str(agent_path)],
        cwd=str(agent_path.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid  # Create new process group for clean shutdown
    )
    
    # Wait for server to start (adjust timeout if needed)
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get("http://localhost:8080/ping", timeout=1)
            if response.status_code == 200:
                break
        except requests.exceptions.RequestException:
            time.sleep(0.5)
    else:
        # Server didn't start in time
        process.kill()
        stdout, stderr = process.communicate()
        pytest.fail(f"Server failed to start.\nStdout: {stdout.decode()}\nStderr: {stderr.decode()}")
    
    yield process
    
    # Cleanup: terminate the server process and its children
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=5)
    except Exception:
        process.kill()


def test_agent_core_invoke_research_query(agent_server):
    """Test the scoping agent core with a research prompt."""
    url = "http://localhost:8080/invocations"
    headers = {"Content-Type": "application/json"}
    payload = {
        "prompt": "I want to research the best coffee shops in San Francisco.",
        "thread_id": "test-thread-1"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert "messages" in data
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) > 0
    assert len(data["messages"][-1]['content']) > 0


def test_agent_core_invoke_followup(agent_server):
    """Test the scoping agent core with a followup prompt in the same thread."""
    url = "http://localhost:8080/invocations"
    headers = {"Content-Type": "application/json"}
    
    # First message
    payload_1 = {
        "prompt": "I want to research the best coffee shops in San Francisco.",
        "thread_id": "test-thread-2"
    }
    
    response_1 = requests.post(url, json=payload_1, headers=headers)
    assert response_1.status_code == 200
    data_1 = response_1.json()
    assert "messages" in data_1
    
    # Followup message in the same thread
    payload_2 = {
        "prompt": "Let's focus on coffee bean grading and sourcing quality",
        "thread_id": "test-thread-2"  # Same thread
    }
    
    response_2 = requests.post(url, json=payload_2, headers=headers)
    assert response_2.status_code == 200
    data_2 = response_2.json()
    assert "messages" in data_2
    assert "research_brief" in data_2
    assert isinstance(data_2["research_brief"], str)
    assert len(data_2["research_brief"]) > 10