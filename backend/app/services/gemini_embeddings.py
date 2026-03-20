"""
Gemini multimodal embeddings — DISABLED.

The experimental Gemini embedding model has been retired and returns 404.
Text-based vector search via OpenAI embeddings handles all retrieval.
These stubs remain so existing imports don't break.
"""

from __future__ import annotations


def is_available() -> bool:
    return False


def embed_image(image_bytes: bytes) -> list[float]:
    raise RuntimeError("Gemini embeddings are disabled (model retired)")


def embed_text(text: str) -> list[float]:
    raise RuntimeError("Gemini embeddings are disabled (model retired)")
