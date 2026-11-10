# One image recipe for all eight services. Build from the repository root:
#   docker build -f services/Dockerfile --build-arg SERVICE=price_history -t price-history .
FROM python:3.12-slim
ARG SERVICE
ENV SERVICE=${SERVICE} PORT=8000
WORKDIR /app
COPY libs/python /app/libs/python
COPY services /app/services
RUN pip install --no-cache-dir /app/libs/python /app/services
EXPOSE 8000
CMD ["sh", "-c", "uvicorn ${SERVICE}.main:app --host 0.0.0.0 --port ${PORT}"]
