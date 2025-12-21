"""LangGraph Worker-Evaluator Agent with Math Tools.

A simple agent that uses a worker-evaluator pattern to answer math questions.
"""

import json
import os
from typing import Any, Annotated, Iterator, Literal, TypedDict
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.tools import tool
from langchain_aws import ChatBedrock
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from operator import add


# ===== MATH TOOLS =====

@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        The sum of a and b
    """
    return a + b


@tool
def subtract_numbers(a: float, b: float) -> float:
    """Subtract b from a.
    
    Args:
        a: First number
        b: Number to subtract
        
    Returns:
        The result of a - b
    """
    return a - b


@tool
def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers together.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        The product of a and b
    """
    return a * b


@tool
def divide_numbers(a: float, b: float) -> float:
    """Divide a by b.
    
    Args:
        a: Numerator
        b: Denominator (must not be zero)
        
    Returns:
        The result of a / b
        
    Raises:
        ValueError: If b is zero
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


# ===== STATE DEFINITION =====

class WorkerEvaluatorState(TypedDict):
    """State for the worker-evaluator agent."""
    messages: Annotated[list[BaseMessage], add]
    worker_output: str
    evaluation_result: str


# ===== CONFIGURATION =====

# Initialize Bedrock Claude Sonnet 4.5 (v2)
_bedrock_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-west-2"
model = ChatBedrock(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name=_bedrock_region,
)

# Create tool list and bind to model
tools = [add_numbers, subtract_numbers, multiply_numbers, divide_numbers]
model_with_tools = model.bind_tools(tools)

# Create tool node for executing tools
tool_node = ToolNode(tools)


# ===== AGENT NODES =====

def worker(state: WorkerEvaluatorState) -> dict:
    """
    Worker node that processes the user's question and uses math tools.
    The worker attempts to solve the math problem using available tools.
    """
    messages = state["messages"]
    
    # Add system message for the worker
    system_prompt = SystemMessage(content="""You are a mathematical worker agent. 
Your job is to solve math problems using the available tools: add_numbers, subtract_numbers, 
multiply_numbers, and divide_numbers. Break down complex problems step by step.
Use tools to perform calculations and show your work.""")
    
    worker_messages = [system_prompt] + messages
    
    # Invoke the model with tools
    response = model_with_tools.invoke(worker_messages)

    # Only persist `worker_output` when the worker has produced a final response
    # (i.e., no tool calls are pending). This prevents routing to the evaluator
    # prematurely right after the first tool-use turn.
    worker_output = ""
    if not (hasattr(response, "tool_calls") and response.tool_calls):
        worker_output = str(response.content or "")

    return {
        "messages": [response],
        "worker_output": worker_output,
    }


def evaluator(state: WorkerEvaluatorState) -> dict:
    """
    Evaluator node that checks the worker's output for correctness.
    The evaluator reviews the calculation steps and validates the answer.
    """
    messages = state["messages"]
    worker_output = state.get("worker_output", "")
    question = ""
    if messages and isinstance(messages[0], HumanMessage):
        question = messages[0].content
    
    # Add system message for the evaluator
    system_prompt = SystemMessage(content=f"""You are an evaluation agent that checks mathematical work.
Review the worker's calculations and verify they are correct. 

Worker's output: {worker_output}

Check:
1. Are the calculation steps logical?
2. Are the tool calls appropriate?
3. Is the final answer correct?

If everything is correct, approve it. If there are errors, point them out.""")
    
    # Keep evaluation context tight so the evaluator evaluates instead of continuing to solve.
    evaluation_messages = [
        system_prompt,
        HumanMessage(
            content=(
                f"Question: {question}\n\n"
                f"Worker answer (verbatim):\n{worker_output}\n"
            )
        ),
    ]
    
    # Invoke the model for evaluation
    response = model.invoke(evaluation_messages)
    
    return {
        "messages": [response],
        "evaluation_result": str(response.content)
    }


# ===== ROUTING LOGIC =====

def should_continue(state: WorkerEvaluatorState) -> Literal["tools", "evaluator"] | str:
    """
    Determine the next step based on the current state.
    
    - If the last message has tool calls, route to tools
    - If we have worker output but no evaluation, route to evaluator
    - Otherwise, end the conversation
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # If there are tool calls, execute them
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    
    # If we have worker output but haven't evaluated yet
    if state.get("worker_output") and not state.get("evaluation_result"):
        return "evaluator"
    
    # Otherwise, we're done
    return END


def route_after_tools(state: WorkerEvaluatorState) -> Literal["worker", "evaluator"]:
    """
    After executing tools, decide whether to continue with worker or move to evaluator.
    
    - If we have unevaluated worker output, go to evaluator
    - Otherwise, continue with worker
    """
    # After tools execute, always return to the worker so it can incorporate tool results
    # and produce a final answer before evaluation.
    return "worker"


# ===== GRAPH CONSTRUCTION =====

# Build the worker-evaluator graph
builder = StateGraph(WorkerEvaluatorState)

# Add nodes
builder.add_node("worker", worker)
builder.add_node("tools", tool_node)
builder.add_node("evaluator", evaluator)

# Add edges
builder.add_edge(START, "worker")
builder.add_conditional_edges("worker", should_continue)
builder.add_conditional_edges("tools", route_after_tools)
builder.add_edge("evaluator", END)

# Compile the graph
graph = builder.compile()


# ===== ENTRY POINT =====

def answer_math_question(question: str) -> dict:
    """
    Answer a math question using the worker-evaluator agent.
    
    Args:
        question: The math question to answer
        
    Returns:
        Dictionary with the full conversation and final result
    """
    result = graph.invoke({
        "messages": [HumanMessage(content=question)],
        "worker_output": "",
        "evaluation_result": ""
    })
    
    return {
        "question": question,
        "messages": result["messages"],
        "worker_output": result.get("worker_output", ""),
        "evaluation_result": result.get("evaluation_result", ""),
        "final_answer": result["messages"][-1].content if result["messages"] else ""
    }


def answer_math_question_streaming(
    question: str,
    *,
    stream_mode: Literal["updates", "values"] = "updates",
) -> Iterator[dict[str, Any]]:
    """Stream each graph step back to the caller.

    Yields one event per node execution.

    Event shape:
      {"node": <node_name>, "update": <partial_state_update>}   (stream_mode="updates")
      {"node": "__values__", "values": <full_state>}           (stream_mode="values")
    """

    initial_state: WorkerEvaluatorState = {
        "messages": [HumanMessage(content=question)],
        "worker_output": "",
        "evaluation_result": "",
    }

    def _serialize_message(msg: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": msg.__class__.__name__,
        }
        if hasattr(msg, "content"):
            data["content"] = msg.content
        if hasattr(msg, "name") and getattr(msg, "name"):
            data["name"] = msg.name
        if hasattr(msg, "tool_call_id") and getattr(msg, "tool_call_id"):
            data["tool_call_id"] = msg.tool_call_id
        if hasattr(msg, "tool_calls") and getattr(msg, "tool_calls"):
            data["tool_calls"] = msg.tool_calls
        return data

    def _json_safe(value: Any) -> Any:
        """Best-effort conversion to JSON-serializable data."""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [_json_safe(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        # LangChain messages
        if isinstance(value, BaseMessage) or hasattr(value, "content"):
            return _serialize_message(value)

        # Fallback: try native JSON; otherwise string-repr
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    if stream_mode == "updates":
        for event in graph.stream(initial_state, stream_mode="updates"):
            # `event` is a dict keyed by node name -> partial update
            for node_name, node_update in event.items():
                payload: dict[str, Any] = {"node": node_name}
                if isinstance(node_update, dict):
                    if "messages" in node_update and node_update["messages"]:
                        payload["messages"] = [_serialize_message(m) for m in node_update["messages"]]
                    if "worker_output" in node_update and node_update["worker_output"]:
                        payload["worker_output"] = node_update["worker_output"]
                    if "evaluation_result" in node_update and node_update["evaluation_result"]:
                        payload["evaluation_result"] = node_update["evaluation_result"]
                yield payload
        return

    # stream_mode == "values"
    for values in graph.stream(initial_state, stream_mode="values"):
        yield {"node": "__values__", "values": _json_safe(values)}


if __name__ == "__main__":
    # Minimal streaming demo (no question-loop prints).
    question = "What is (10 + 5) * 3?"
    for step in answer_math_question_streaming(question, stream_mode="values"):
        print(json.dumps(step, ensure_ascii=False))
