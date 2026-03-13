"""
Gemini multimodal embeddings service.

Uses the google-genai SDK to generate 768-dim embeddings for both images
and text queries, enabling visual document page retrieval.

When GOOGLE_AI_API_KEY is not configured, all public functions degrade
gracefully (is_available() returns False, embed_* raise RuntimeError).
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GEMINI_EMBED_MODEL = "gemini-embedding-exp-03-07"


# ---------------------------------------------------------------------------
# Client helper
# ---------------------------------------------------------------------------


def _get_client():
    """Return a google.genai.Client, or None if the API key is missing."""
    settings = get_settings()
    if not settings.google_ai_api_key:
        return None

    from google import genai

    return genai.Client(api_key=settings.google_ai_api_key)


def is_available() -> bool:
    """Return True when GOOGLE_AI_API_KEY is configured."""
    return bool(get_settings().google_ai_api_key)


# ---------------------------------------------------------------------------
# Embedding functions
# ---------------------------------------------------------------------------


def embed_image(image_bytes: bytes) -> list[float]:
    """
    Generate a 768-dim embedding for a JPEG image.

    Raises RuntimeError if Gemini is not configured.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("Gemini API not configured (GOOGLE_AI_API_KEY missing)")

    from google.genai import types

    result = client.models.embed_content(
        model=GEMINI_EMBED_MODEL,
        contents=types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
    )

    return list(result.embeddings[0].values)


def embed_text(text: str) -> list[float]:
    """
    Generate a 768-dim embedding for a text query using Gemini.

    This allows text-to-image similarity search against page image embeddings.
    Raises RuntimeError if Gemini is not configured.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("Gemini API not configured (GOOGLE_AI_API_KEY missing)")

    result = client.models.embed_content(
        model=GEMINI_EMBED_MODEL,
        contents=text,
    )

    return list(result.embeddings[0].values)


def embed_image_batch(images: list[bytes]) -> list[Optional[list[float]]]:
    """
    Generate embeddings for a batch of images.

    Returns a list of embeddings (or None for any that failed).
    """
    results: list[Optional[list[float]]] = []
    for img_bytes in images:
        try:
            results.append(embed_image(img_bytes))
        except Exception as exc:
            logger.warning("Gemini image embedding failed for one image: %s", exc)
            results.append(None)
    return results
