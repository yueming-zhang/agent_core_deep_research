from pathlib import Path
import sys
import dotenv

# Load environment variables BEFORE importing modules that need them
dotenv.load_dotenv(Path(__file__).parents[3] / '.env')

sys.path.append(str(Path(__file__).parents[2]))

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from deep_research.research_agent_scope import deep_researcher_builder
from utils import format_messages
from agent_core.scoping_agent_core import langgraph_bedrock


@pytest.fixture
def agent_with_checkpointer():
    checkpointer = InMemorySaver()
    scope = deep_researcher_builder.compile(checkpointer=checkpointer)
    return scope


def test_coffee_shop_research(agent_with_checkpointer):
    scope = agent_with_checkpointer
    thread = {"configurable": {"thread_id": "1"}}
    
    result = scope.invoke(
        {"messages": [HumanMessage(content="I want to research the best coffee shops in San Francisco.")]},
        config=thread
    )
    
    assert "messages" in result
    assert len(result["messages"]) > 0
    assert result["messages"][-1].content

    # send another message to clarify the request
    result = scope.invoke(
        {"messages": [HumanMessage(content="Let's focus on coffee quality?")]},
        config=thread
    )

    assert len(result['research_brief']) > 10

def test_agent_core_entrypoint():
    payload = {
        "prompt": "I want to research the best coffee shops in San Francisco.",
        "thread_id": "test-thread-1"
    }
    
    result = langgraph_bedrock(payload)
    assert 'best' in result['messages'][-1].content

    result = langgraph_bedrock({
        "prompt": "Let's focus on coffee bean grading and sourcing quality",
        "thread_id": "test-thread-1"  # Same thread
    })

    assert len(result['research_brief']) > 10
