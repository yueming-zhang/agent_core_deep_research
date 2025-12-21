"""AgentCore Runtime entrypoint for the LangGraph worker/evaluator math agent.

Implements streaming via an async generator:
- Each `yield` is turned into a Server-Sent Events (SSE) `data:` chunk by AgentCore.
- The yielded object should be JSON-serializable.

Local run:
  /workspaces/agent_core_deep_research/.venv/bin/python -m langgraph_streaming.agentcore_langgraph_math_streaming

Local invoke (streams SSE):
  curl -N -X POST http://localhost:8080/invocations \
    -H 'Content-Type: application/json' \
    -d '{"prompt": "What is (10 + 5) * 3?"}'
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp

# When executed as a script, Python sets `sys.path[0]` to this folder
# (`langgraph_streaming/`), which prevents importing `langgraph_streaming.*`.
# Ensure the repo root is on sys.path for local runs.
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
  sys.path.insert(0, str(_repo_root))

# Import the graph streaming helper (server-side adaptor)
from langgraph_streaming.worker_evaluator_math_agent import (
  answer_math_question,
  answer_math_question_streaming,
)

app = BedrockAgentCoreApp()


async def _invoke_stream(payload: dict[str, Any]):
  """Stream LangGraph step events as SSE chunks."""

  user_input = payload.get("prompt", "")
  stream_mode = payload.get("stream_mode", "updates")  # "updates" | "values"

  try:
    for event in answer_math_question_streaming(user_input, stream_mode=stream_mode):
      yield event
  except Exception as e:
    yield {"type": "stream_error", "error": str(e)}


@app.entrypoint
async def invoke(payload: dict[str, Any]):
  """AgentCore entrypoint.

  Default: normal (non-streaming) JSON response.
  Streaming: set `{"stream": true}` in the payload to receive SSE.
  """

  # Default to normal invoke. Streaming is opt-in.
  want_stream = bool(payload.get("stream") or payload.get("streaming"))
  if want_stream:
    return _invoke_stream(payload)

  user_input = payload.get("prompt", "")
  try:
    result = answer_math_question(user_input)
    final_answer = result.get("final_answer") or result.get("worker_output") or ""
    return {
      "result": final_answer,
      "worker_output": result.get("worker_output", ""),
      "evaluation_result": result.get("evaluation_result", ""),
    }
  except Exception as e:
    return {"type": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
