"""
Hybrid search: combines pgvector semantic search with PostgreSQL BM25 full-text search.
Results are merged using Reciprocal Rank Fusion (RRF).
"""


def reciprocal_rank_fusion(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """
    Merge multiple ranked result lists using RRF.
    Each item in ranked_lists is a list of dicts with at least 'id' and 'score' keys.
    k=60 is the standard RRF constant that prevents high-ranked items from dominating.
    Returns a single merged list sorted by RRF score, descending.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list):
            item_id = str(item['id'])
            if item_id not in scores:
                scores[item_id] = 0.0
                items[item_id] = item
            scores[item_id] += 1.0 / (k + rank + 1)  # rank is 0-indexed

    # Sort by RRF score descending
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    result = []
    for item_id in sorted_ids:
        item = items[item_id].copy()
        item['rrf_score'] = scores[item_id]
        result.append(item)

    return result
