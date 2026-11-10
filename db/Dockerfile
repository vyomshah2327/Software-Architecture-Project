# One-off job that creates the schema, the least-privilege roles and the sample data.
# Build from the repository root:  docker build -f db/Dockerfile -t db-init .
FROM python:3.12-slim
WORKDIR /app
COPY libs/python /app/libs/python
COPY db /app/db
RUN pip install --no-cache-dir /app/libs/python
CMD ["python", "db/init_db.py", "--seed", "--roles"]
