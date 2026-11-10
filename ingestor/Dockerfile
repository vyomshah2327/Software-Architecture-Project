# Build from the repository root:  docker build -f ingestor/Dockerfile -t ingestor .
# Runs once and exits, so it suits a Code Engine job on a daily schedule.
FROM python:3.12-slim
WORKDIR /app
COPY libs/python /app/libs/python
COPY ingestor /app/ingestor
RUN pip install --no-cache-dir /app/libs/python /app/ingestor
CMD ["python", "-m", "ingestor.run"]
