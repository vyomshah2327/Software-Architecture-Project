# Build from the repository root:  docker build -f registry/Dockerfile -t registry .
FROM python:3.12-slim
WORKDIR /app
COPY libs/python /app/libs/python
COPY registry /app/registry
RUN pip install --no-cache-dir /app/libs/python /app/registry
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn registry.main:app --host 0.0.0.0 --port ${PORT}"]
