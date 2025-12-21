"""Minimal client for AgentCore invoke (normal or streaming).

Usage:
  /workspaces/agent_core_deep_research/.venv/bin/python \
    langgraph_streaming/client_invoke_streaming.py \
    --prompt "What is (10 + 5) * 3?" \
        --stream

Normal (default):
    /workspaces/agent_core_deep_research/.venv/bin/python \
        langgraph_streaming/client_invoke_streaming.py \
        --prompt "What is (10 + 5) * 3?"

Notes:
- Default behavior is a normal JSON response.
- With `--stream`, AgentCore streams Server-Sent Events (SSE).
- Each server `yield` becomes an SSE `data:` line.
- Streaming mode reads lines, extracts `data: ...`, and JSON-decodes when possible.
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
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Enable SSE streaming (default: off / normal JSON response)",
    )
    parser.add_argument(
        "--stream-mode",
        default="updates",
        choices=["updates", "values"],
        help="Streaming mode (only used with --stream)",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    payload: Dict[str, Any] = {"prompt": args.prompt}

    if not args.stream:
        resp = requests.post(args.url, json=payload, timeout=args.timeout)
        resp.raise_for_status()
        # Server returns JSON; fall back to raw text if not JSON.
        try:
            data = resp.json()
        except ValueError:
            data = {"type": "data", "data": resp.text}
        print(json.dumps(data, ensure_ascii=False))
        return 0

    payload["stream"] = True
    payload["stream_mode"] = args.stream_mode

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
                continue

            print(json.dumps(event, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
