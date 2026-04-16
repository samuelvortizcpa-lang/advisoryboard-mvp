"""Unit tests for _build_bm25_or_tsquery_string helper."""

from app.services.rag_service import _build_bm25_or_tsquery_string


def test_simple_query():
    assert _build_bm25_or_tsquery_string("AGI 2024") == "agi | 2024"


def test_question_form():
    # Punctuation and apostrophes are stripped via the regex.
    # Stopwords like 'what', 'is', 'for' are kept here — to_tsquery
    # handles stopword removal at query time.
    result = _build_bm25_or_tsquery_string("What is Michael's AGI for 2024?")
    assert result is not None
    assert "michael" in result
    assert "agi" in result
    assert "2024" in result
    assert " | " in result  # OR-joined


def test_empty_query():
    assert _build_bm25_or_tsquery_string("") is None
    assert _build_bm25_or_tsquery_string("???") is None
    assert _build_bm25_or_tsquery_string("a b c") is None  # all single-char


def test_dedup():
    result = _build_bm25_or_tsquery_string("tax tax tax 2024")
    # 'tax' should appear once, not three times
    assert result is not None
    assert result.count("tax") == 1


def test_punctuation_handling():
    result = _build_bm25_or_tsquery_string("W-2 wages, $271,792")
    # Should produce tokens; should not produce a malformed tsquery string
    assert result is not None
    assert "wages" in result
    # No special chars that would break to_tsquery
    assert ";" not in result and "(" not in result and ")" not in result


def test_preserves_order():
    result = _build_bm25_or_tsquery_string("income total 2024")
    assert result == "income | total | 2024"


def test_single_valid_token():
    result = _build_bm25_or_tsquery_string("income")
    assert result == "income"
