"""Invoke a deployed Amazon Bedrock AgentCore Runtime and print streaming events.

This client calls the AgentCore control plane (boto3) using your runtime ARN.
If the runtime streams SSE (Content-Type: text/event-stream), this script prints
one JSON object per SSE `data:` line.

Usage:
  python langgraph_streaming/client_invoke_deployed_runtime.py \
    --arn arn:aws:bedrock-agentcore:us-west-2:482387069690:runtime/langgraph_math_streaming-D1rmXq5o62 \
    --prompt "What is (10 + 5) * 3?" \
    --stream-mode updates
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Optional

import boto3


def _json_dumps(obj: Any) -> str:
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _try_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def _handle_sse_lines(stream: Any) -> None:
    """Read SSE lines from a StreamingBody-like object and print parsed data events."""

    # Botocore StreamingBody implements iter_lines().
    for raw_line in stream.iter_lines(chunk_size=1):
        if not raw_line:
            continue

        line = raw_line.decode("utf-8") if isinstance(raw_line, (bytes, bytearray)) else str(raw_line)
        line = line.strip()
        if not line:
            continue

        if not line.startswith("data:"):
            continue

        payload = line[len("data:") :].strip()
        if not payload:
            continue

        parsed = _try_json_loads(payload)
        if isinstance(parsed, dict):
            print(_json_dumps(parsed))
        else:
            print(_json_dumps({"type": "data", "data": parsed}))


def _extract_bytes_from_event(event: Any) -> Optional[bytes]:
    """Best-effort extraction of bytes from various streamed event shapes."""

    if isinstance(event, (bytes, bytearray)):
        return bytes(event)

    if isinstance(event, dict):
        # Common botocore EventStream shapes:
        #  - {"chunk": {"bytes": b"..."}}
        #  - {"bytes": b"..."}
        chunk = event.get("chunk")
        if isinstance(chunk, dict) and isinstance(chunk.get("bytes"), (bytes, bytearray)):
            return bytes(chunk["bytes"])
        if isinstance(event.get("bytes"), (bytes, bytearray)):
            return bytes(event["bytes"])

    return None


def _handle_eventstream(stream: Any) -> None:
    """Handle botocore EventStream-like iterables by printing chunked data."""

    buffer = b""
    for event in stream:
        payload_bytes = _extract_bytes_from_event(event)
        if payload_bytes is None:
            # Fall back to printing the raw event if it's JSON-serializable.
            try:
                print(_json_dumps({"type": "event", "event": event}))
            except TypeError:
                print(_json_dumps({"type": "event", "event": str(event)}))
            continue

        buffer += payload_bytes

        # SSE frames are line-oriented; flush complete lines as they arrive.
        while b"\n" in buffer:
            line_bytes, buffer = buffer.split(b"\n", 1)
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data:
                continue
            parsed = _try_json_loads(data)
            if isinstance(parsed, dict):
                print(_json_dumps(parsed))
            else:
                print(_json_dumps({"type": "data", "data": parsed}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--arn",
        default=(
            os.getenv("AGENTCORE_RUNTIME_ARN")
            or "arn:aws:bedrock-agentcore:us-west-2:482387069690:runtime/langgraph_math_streaming-D1rmXq5o62"
        ),
        help=(
            "Agent runtime ARN (arn:aws:bedrock-agentcore:...:runtime/...). "
            "Defaults to $AGENTCORE_RUNTIME_ARN if set, otherwise a repo-local example ARN."
        ),
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-west-2",
    )
    parser.add_argument("--qualifier", default="DEFAULT")
    parser.add_argument(
        "--prompt",
        default="What is (10 + 5) * 3?",
        help="Prompt to send to the agent",
    )
    parser.add_argument(
        "--render-newlines",
        action="store_true",
        help=(
            "After printing JSON, also print multiline string fields with real line breaks. "
            "(JSON must escape newlines as \\n to stay valid.)"
        ),
    )
    parser.add_argument(
        "--stream-mode",
        default="updates",
        choices=["updates", "values"],
        help="Streaming mode",
    )
    args = parser.parse_args()

    if not args.arn:
        print(
            _json_dumps(
                {
                    "type": "error",
                    "error": "Missing runtime ARN. Provide --arn or set AGENTCORE_RUNTIME_ARN.",
                }
            )
        )
        return 2

    client = boto3.client("bedrock-agentcore", region_name=args.region)

    payload_obj: dict[str, Any] = {
        "prompt": args.prompt,
        "stream": True,
        "stream_mode": args.stream_mode,
    }

    resp = client.invoke_agent_runtime(
        agentRuntimeArn=args.arn,
        qualifier=args.qualifier,
        payload=json.dumps(payload_obj),
    )

    content_type = resp.get("contentType", "") or ""
    stream = resp.get("response")

    def _maybe_render_multiline(obj: Any) -> None:
        if not args.render_newlines:
            return
        if not isinstance(obj, dict):
            return
        for key, value in obj.items():
            if isinstance(value, str) and "\n" in value:
                print(f"\n--- {key} ---")
                print(value)

    if stream is None:
        print(_json_dumps({"type": "error", "error": "No response stream in SDK output"}))
        return 2

    # Streaming case: StreamingBody with SSE
    if "text/event-stream" in content_type and hasattr(stream, "iter_lines"):
        _handle_sse_lines(stream)
        return 0

    # Non-streaming case: StreamingBody with JSON/text
    if hasattr(stream, "read"):
        raw = stream.read()
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        parsed = _try_json_loads(text)
        if isinstance(parsed, dict):
            print(_json_dumps(parsed))
            _maybe_render_multiline(parsed)
        else:
            print(_json_dumps({"type": "data", "data": parsed}))
        return 0

    # Some SDKs return botocore.eventstream.EventStream (iterable of events)
    if hasattr(stream, "__iter__"):
        _handle_eventstream(stream)
        return 0

    print(_json_dumps({"type": "unknown_stream", "contentType": content_type, "stream": str(stream)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
