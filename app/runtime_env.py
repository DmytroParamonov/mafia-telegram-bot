from __future__ import annotations

import os
from pathlib import Path


def load_env_value(name: str, env_file: str | Path = ".env") -> str | None:
    """Load one simple KEY=VALUE from .env into os.environ if it is not already set."""
    existing = os.getenv(name)
    if existing is not None:
        return existing

    path = Path(env_file)
    if not path.is_file():
        return None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[name] = value
        return value
    return None
