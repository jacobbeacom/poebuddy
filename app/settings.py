"""Central config loader.

Reads config/settings.yaml plus environment overrides from .env.
Import `SETTINGS` anywhere: `from app.settings import SETTINGS`.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Project root = parent of the app/ package.
ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def _abs(p: str) -> str:
    """Resolve a possibly-relative path against the project root."""
    path = Path(p)
    return str(path if path.is_absolute() else ROOT / path)


@lru_cache(maxsize=1)
def load_settings() -> dict[str, Any]:
    cfg_path = ROOT / "config" / "settings.yaml"
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh)

    # --- environment overrides (env wins over yaml) ---
    cfg["wiki"]["api_url"] = os.getenv("WIKI_API_URL", cfg["wiki"]["api_url"])
    cfg["wiki"]["user_agent"] = os.getenv(
        "WIKI_USER_AGENT",
        "poebuddy/0.1 (personal research tool)",
    )
    cfg["llm"]["host"] = os.getenv("OLLAMA_HOST", cfg["llm"]["host"])
    cfg["llm"]["chat_model"] = os.getenv("CHAT_MODEL", cfg["llm"]["chat_model"])
    cfg["embedding"]["model"] = os.getenv("EMBED_MODEL", cfg["embedding"]["model"])

    # --- resolve paths to absolute ---
    cfg["paths"] = {k: _abs(v) for k, v in cfg["paths"].items()}
    for d in (cfg["paths"]["raw_dir"], cfg["paths"]["normalized_dir"],
              cfg["paths"]["qdrant_path"]):
        Path(d).mkdir(parents=True, exist_ok=True)

    return cfg


SETTINGS: dict[str, Any] = load_settings()
