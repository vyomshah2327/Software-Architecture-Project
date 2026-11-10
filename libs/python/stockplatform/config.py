"""Small helpers for reading configuration from environment variables."""
import os


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_int(name: str, default: int) -> int:
    return int(env(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env(name, str(default)))


def env_bool(name: str, default: bool = False) -> bool:
    return str(env(name, str(default))).lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in (env(name, default) or "").split(",") if item.strip()]
