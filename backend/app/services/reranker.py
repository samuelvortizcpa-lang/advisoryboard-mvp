"""
Cross-encoder reranking using Cohere Rerank API.
Gracefully skips if COHERE_API_KEY is not set.
"""

import logging
import os

import sentry_sdk

logger = logging.getLogger(__name__)

_cohere_client = None


def _get_client():
    global _cohere_client
    if _cohere_client is None:
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            return None
        import cohere
        _cohere_client = cohere.AsyncClientV2(
            api_key=api_key,
            timeout=5.0,
        )
    return _cohere_client


async def rerank_chunks(
    query: str,
    chunks: list[dict],
    top_k: int = 5,
) -> tuple[list[dict], bool]:
    """
    Rerank chunks using Cohere's cross-encoder.
    Returns (reranked_chunks, did_rerank).
    Falls back to (chunks[:top_k], False) if reranking unavailable.
    """
    client = _get_client()
    if client is None:
        logger.info("Reranking skipped: COHERE_API_KEY not configured")
        return chunks[:top_k], False

    if len(chunks) <= top_k:
        return chunks, False

    try:
        documents = [c["chunk_text"] for c in chunks]
        response = await client.rerank(
            model="rerank-v3.5",
            query=query,
            documents=documents,
            top_n=top_k,
            return_documents=False,
        )

        reranked = []
        for result in response.results:
            chunk = chunks[result.index].copy()
            chunk["rerank_score"] = result.relevance_score
            reranked.append(chunk)

        scores_str = ", ".join(
            "%.3f" % r["rerank_score"] for r in reranked
        )
        logger.info(
            "Reranked %d candidates to top %d (scores: %s)",
            len(chunks), len(reranked), scores_str,
        )
        return reranked, True

    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logger.warning("Reranking failed, using unranked results", exc_info=True)
        return chunks[:top_k], False
