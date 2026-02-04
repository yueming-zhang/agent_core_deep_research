#!/usr/bin/env python3
import boto3, json, argparse, uuid

AGENT_NAME = "dr_poc_agent"

def get_agent_runtime_arn(region):
    client = boto3.client("bedrock-agentcore-control", region_name=region)
    for page in client.get_paginator("list_agent_runtimes").paginate():
        for runtime in page.get("agentRuntimes", []):
            if runtime["agentRuntimeName"] == AGENT_NAME:
                return runtime["agentRuntimeArn"]
    return None

def invoke_agent(arn, prompt, session_id, thread_id, region):
    client = boto3.client("bedrock-agentcore", region_name=region)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn, qualifier="DEFAULT", runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt, "thread_id": thread_id})
    )
    return "".join(event.decode("utf-8") for event in response.get("response", []))

def main():
    parser = argparse.ArgumentParser(description="Interactive CLI for AgentCore runtime")
    parser.add_argument("--actor-id", required=True, help="Actor ID for the session")
    parser.add_argument("--region", required=True, help="AWS region")
    args = parser.parse_args()

    arn = get_agent_runtime_arn(args.region)
    if not arn:
        print(f"Error: Agent runtime '{AGENT_NAME}' not found in {args.region}")
        return

    print(f"Connected to agent: {AGENT_NAME} ({args.region})")
    print(f"Actor ID: {args.actor_id}")
    print("Type 'quit' or 'exit' to end the session.\n")

    session_id, thread_id = f"session-{uuid.uuid4()}", args.actor_id
    while True:
        try:
            user_input = input(f"{args.actor_id}> ").strip()
            if user_input.lower() in ("quit", "exit"):
                break
            if not user_input:
                continue
            response = invoke_agent(arn, user_input, session_id, thread_id, args.region)
            print(f"{args.actor_id}: {response}\n")
        except KeyboardInterrupt:
            break
    print("\nSession ended.")

if __name__ == "__main__":
    main()
#python agent_cli.py --region us-west-2 --actor-id my-user
#python agent_cli.py --region eu-west-1 --actor-id my-user