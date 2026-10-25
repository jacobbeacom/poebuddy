"""Thin wrapper around the local Ollama API for chat + embeddings.

Everything runs on localhost; nothing is sent to a remote service.
"""
from __future__ import annotations

from typing import Iterator

import ollama

from app.settings import SETTINGS

_LLM = SETTINGS["llm"]
_EMBED = SETTINGS["embedding"]

_client = ollama.Client(host=_LLM["host"])


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return one embedding vector per input string."""
    vectors: list[list[float]] = []
    for t in texts:
        resp = _client.embeddings(model=_EMBED["model"], prompt=t)
        vectors.append(resp["embedding"])
    return vectors


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]


def chat(messages: list[dict], *, temperature: float | None = None,
         fmt: str | dict | None = None) -> str:
    """Non-streaming chat completion. `fmt` may be 'json' or a JSON schema dict."""
    options = {
        "temperature": _LLM["temperature"] if temperature is None else temperature,
        "num_ctx": _LLM["num_ctx"],
    }
    kwargs = {"model": _LLM["chat_model"], "messages": messages, "options": options}
    if fmt is not None:
        kwargs["format"] = fmt
    resp = _client.chat(**kwargs)
    return resp["message"]["content"]


def chat_stream(messages: list[dict],
                *, temperature: float | None = None) -> Iterator[str]:
    """Yield content tokens as they arrive (for the Streamlit UI)."""
    options = {
        "temperature": _LLM["temperature"] if temperature is None else temperature,
        "num_ctx": _LLM["num_ctx"],
    }
    for part in _client.chat(
        model=_LLM["chat_model"], messages=messages, options=options, stream=True
    ):
        token = part.get("message", {}).get("content", "")
        if token:
            yield token
