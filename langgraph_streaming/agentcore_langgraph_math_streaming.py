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
from langgraph_streaming.worker_evaluator_math_agent import answer_math_question_streaming

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict[str, Any]):
    """AgentCore entrypoint that streams LangGraph step events."""

    user_input = payload.get("prompt", "")
    stream_mode = payload.get("stream_mode", "updates")  # "updates" | "values"

    try:
        for event in answer_math_question_streaming(user_input, stream_mode=stream_mode):
            # `event` is a dict (JSON-safe in values-mode; mostly JSON-safe in updates-mode)
            yield event
    except Exception as e:
        # Errors should still be streamed so the client can render them.
        yield {"type": "stream_error", "error": str(e)}


if __name__ == "__main__":
    app.run()
