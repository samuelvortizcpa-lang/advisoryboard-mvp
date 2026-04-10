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


if __name__ == "__main__":
    import asyncio

    async def _smoke_test():
        sample_chunks = [
            {"chunk_text": "The client's 2024 W-2 shows gross wages of $145,000."},
            {"chunk_text": "Meeting notes from March: discussed Roth conversion strategy."},
            {"chunk_text": "Form 1099-DIV reports $3,200 in qualified dividends."},
            {"chunk_text": "The engagement letter was signed on January 15, 2024."},
            {"chunk_text": "Schedule C net profit was $87,500 for the tax year."},
            {"chunk_text": "Client asked about estimated tax payment deadlines."},
        ]
        query = "What was the client's W-2 income?"
        results, did_rerank = await rerank_chunks(query, sample_chunks, top_k=3)
        print(f"did_rerank={did_rerank}, results={len(results)}")
        for r in results:
            score = r.get("rerank_score", "N/A")
            print(f"  score={score}  text={r['chunk_text'][:60]}")

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_smoke_test())
