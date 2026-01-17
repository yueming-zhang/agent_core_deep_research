"""Minimal verification script for the deployed AgentCore runtime.

This is intentionally a plain script (no pytest) and uses a hard-coded runtime ARN.
It exits with non-zero status if the invocation doesn't return a non-empty result.
"""

from __future__ import annotations

import json
import sys

import boto3


REGION = "us-west-2"
QUALIFIER = "DEFAULT"
AGENT_RUNTIME_ARN = (
    "arn:aws:bedrock-agentcore:us-west-2:482387069690:runtime/multiserver_mcp_agent-QlSXuKFOnc"
)


def invoke(prompt: str) -> dict:
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        qualifier=QUALIFIER,
        payload=json.dumps({"prompt": prompt}),
    )

    stream = resp.get("response")
    if stream is None or not hasattr(stream, "read"):
        raise RuntimeError("No readable response body from AgentCore invoke")

    raw = stream.read()
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    return json.loads(text)


def main() -> int:
    out = invoke("What is 15 + 27?")
    if not isinstance(out, dict):
        raise RuntimeError(f"Unexpected response type: {type(out)}")

    result = out.get("result")
    if not isinstance(result, str) or not result.strip():
        raise RuntimeError(f"Missing/empty 'result' in response: {out}")

    print("OK")
    print("Runtime:", AGENT_RUNTIME_ARN)
    print("Result:", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAILED")
        print(str(e))
        raise SystemExit(2)

