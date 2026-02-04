FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py agent_runtime.py multi_region_memory_saver.py ./

EXPOSE 8080

CMD ["python", "agent_runtime.py"]