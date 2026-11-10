"""Entry point: ``uvicorn registry.main:app``. Primary and backup run this same image."""
import redis

from stockplatform.config import env

from .app import create_app

app = create_app(redis.Redis.from_url(env("REDIS_URL", "redis://localhost:6379/0")))
