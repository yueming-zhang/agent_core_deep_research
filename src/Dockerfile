FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

# All environment variables in one layer
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    AWS_REGION=us-west-2 \
    AWS_DEFAULT_REGION=us-west-2





# Signal that this is running in Docker for host binding logic
ENV DOCKER_CONTAINER=1

# Install curl
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN uv pip install aws-opentelemetry-distro>=0.10.1

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv pip install --no-cache -e .

# Create non-root user
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 9000
EXPOSE 8000
EXPOSE 8080

ENV PYTHONPATH="/app/src"

CMD ["opentelemetry-instrument", "python", "-m", "agent_core.scoping_agent_core"]
