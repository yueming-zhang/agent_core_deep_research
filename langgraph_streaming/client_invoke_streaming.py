"""Minimal client for streaming AgentCore SSE events.

Usage:
  /workspaces/agent_core_deep_research/.venv/bin/python \
    langgraph_streaming/client_invoke_streaming.py \
    --prompt "What is (10 + 5) * 3?" \
    --stream-mode updates

Notes:
- AgentCore streams Server-Sent Events (SSE).
- Each server `yield` becomes an SSE `data:` line.
- This client reads lines, extracts `data: ...`, and JSON-decodes when possible.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional

import requests


def _parse_sse_data_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse one SSE line (already decoded) into a JSON object when possible."""

    # Typical SSE framing from AgentCore:
    #   data: {"type":"...", ...}
    # Plus possible blank lines and other fields.
    if not line.startswith("data:"):
        return None

    raw = line[len("data:") :].strip()
    if not raw:
        return None

    # Common cases:
    # - Raw is JSON object/array
    # - Raw is a JSON string (quoted)
    # - Raw is plain text
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"type": "data", "data": raw}

    if isinstance(parsed, dict):
        return parsed
    return {"type": "data", "data": parsed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080/invocations")
    parser.add_argument(
        "--prompt",
        default="What is (10 + 5) * 3?",
        help="Prompt to send to the agent (default: a simple math question)",
    )
    parser.add_argument("--stream-mode", default="updates", choices=["updates", "values"])
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    payload = {"prompt": args.prompt, "stream_mode": args.stream_mode}

    with requests.post(
        args.url,
        json=payload,
        stream=True,
        timeout=args.timeout,
        headers={"Accept": "text/event-stream"},
    ) as resp:
        resp.raise_for_status()

        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip()
            if not line:
                continue

            event = _parse_sse_data_line(line)
            if event is None:
                # Uncomment if you want to see non-data SSE fields.
                # print(f"[sse] {line}")
                continue

            print(json.dumps(event, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
