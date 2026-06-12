"""Application runtime settings and shared constants."""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
MAX_TOKENS = _env_int("ANTHROPIC_MAX_TOKENS", 8096)
MAX_ITERATIONS = _env_int("SUPERVISOR_MAX_ITERATIONS", 40)
