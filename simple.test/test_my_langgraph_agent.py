import pytest
import subprocess
import time
import requests
import signal
import os


@pytest.fixture
def agent_server():
    """Start the agent server as a subprocess and clean up after test."""
    # Start the server process
    process = subprocess.Popen(
        ["python", "my_langgraph_agent.py"],
        cwd=os.path.dirname(__file__),
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


def test_agent_invoke_hello(agent_server):
    """Test the agent with a 'Hello!' prompt."""
    url = "http://localhost:8080/invocations"
    headers = {"Content-Type": "application/json"}
    payload = {"prompt": "Hello!"}
    
    response = requests.post(url, json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert "result" in data
    assert isinstance(data["result"], str)
    assert len(data["result"]) > 0  # Response should not be empty


def test_agent_invoke_custom_prompt(agent_server):
    """Test the agent with a custom prompt."""
    url = "http://localhost:8080/invocations"
    headers = {"Content-Type": "application/json"}
    payload = {"prompt": "What is the capital of France?"}
    
    response = requests.post(url, json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert isinstance(data["result"], str)
    assert len(data["result"]) > 0


def test_agent_invoke_no_prompt(agent_server):
    """Test the agent with no prompt (should use default)."""
    url = "http://localhost:8080/invocations"
    headers = {"Content-Type": "application/json"}
    payload = {}
    
    response = requests.post(url, json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert isinstance(data["result"], str)
    assert len(data["result"]) > 0
