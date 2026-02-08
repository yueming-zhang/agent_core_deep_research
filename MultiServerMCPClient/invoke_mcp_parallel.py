import argparse
import asyncio
import sys
import time

import boto3
from boto3.session import Session
from mcp import ClientSession

from streamable_http_sigv4 import streamablehttp_client_with_sigv4


async def main(operation: str = "add_numbers", thread_count: int = 1) -> None:
    boto_session = Session()
    region = boto_session.region_name

    ssm_client = boto3.client("ssm", region_name=region)
    agent_arn_response = ssm_client.get_parameter(Name="/mcp_server/runtime_iam/agent_arn")
    agent_arn = agent_arn_response["Parameter"]["Value"]

    if not agent_arn:
        print("Error: AGENT_ARN not found")
        sys.exit(1)

    encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
    mcp_url = (
        f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    )

    async with streamablehttp_client_with_sigv4(
        url=mcp_url,
        credentials=boto3.Session().get_credentials(),
        service="bedrock-agentcore",
        region=region,
        terminate_on_close=False,
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            n = thread_count
            start = time.perf_counter()
            results = await asyncio.gather(
                *(session.call_tool(operation, {"a": 6, "b": 7}) for _ in range(n))
            )
            duration_s = time.perf_counter() - start
            print(f"Completed {n} parallel {operation} calls in {duration_s:.2f}s")
            print("Results:", [r.structuredContent or r.content for r in results])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MCP tool calls in parallel")
    parser.add_argument(
        "--operation",
        type=str,
        default="add_numbers",
        help="Operation to perform (default: add_numbers)",
    )
    parser.add_argument(
        "--thread-count",
        type=int,
        default=1,
        help="Number of parallel calls (default: 1)",
    )
    args = parser.parse_args()
    
    asyncio.run(main(operation=args.operation, thread_count=args.thread_count))


#python invoke_mcp_parallel.py --operation add_numbers --thread-count 2
#python invoke_mcp_parallel.py --operation multiply_numbers --thread-count 2


#----------
# 10 thread -> 1 session, 22 invocations
# 20 thread -> 1 session, 42 invocations
# 5 thread -> 1 session, 12 invocations
# 1 thread -> 1 session, 4 invocations