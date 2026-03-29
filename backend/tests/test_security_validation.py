"""
Security regression tests — input validation (M5).

Verifies that Pydantic field limits and FastAPI Query bounds reject
oversized or out-of-range input, preventing abuse and resource exhaustion.
"""

import pytest
from pydantic import ValidationError

from app.api.rag import ChatRequest, SearchRequest
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.organization import OrgCreateRequest, AddMemberRequest
from app.api.alerts import DismissRequest
from app.api.documents import _sanitize_filename


# ---------------------------------------------------------------------------
# 1. Client schema string length limits
# ---------------------------------------------------------------------------


class TestClientValidation:
    def test_name_too_long(self):
        with pytest.raises(ValidationError) as exc_info:
            ClientCreate(name="x" * 300)
        assert "max_length" in str(exc_info.value).lower() or "String should have at most" in str(exc_info.value)

    def test_name_empty(self):
        with pytest.raises(ValidationError):
            ClientCreate(name="")

    def test_notes_too_long(self):
        with pytest.raises(ValidationError):
            ClientCreate(name="Valid", notes="x" * 10001)

    def test_custom_instructions_too_long(self):
        with pytest.raises(ValidationError):
            ClientCreate(name="Valid", custom_instructions="x" * 5001)

    def test_valid_client_passes(self):
        c = ClientCreate(name="Alice Corp", notes="Some notes", custom_instructions="Be thorough")
        assert c.name == "Alice Corp"

    def test_update_name_too_long(self):
        with pytest.raises(ValidationError):
            ClientUpdate(name="x" * 300)

    def test_update_notes_too_long(self):
        with pytest.raises(ValidationError):
            ClientUpdate(notes="x" * 10001)


# ---------------------------------------------------------------------------
# 2. RAG request validation
# ---------------------------------------------------------------------------


class TestRagValidation:
    def test_chat_question_too_long(self):
        with pytest.raises(ValidationError):
            ChatRequest(question="x" * 10001)

    def test_chat_question_empty(self):
        with pytest.raises(ValidationError):
            ChatRequest(question="")

    def test_chat_model_override_too_long(self):
        with pytest.raises(ValidationError):
            ChatRequest(question="valid question", model_override="x" * 51)

    def test_search_query_too_long(self):
        with pytest.raises(ValidationError):
            SearchRequest(query="x" * 10001)

    def test_search_query_empty(self):
        with pytest.raises(ValidationError):
            SearchRequest(query="")

    def test_search_limit_too_high(self):
        with pytest.raises(ValidationError):
            SearchRequest(query="valid", limit=100)

    def test_search_limit_zero(self):
        with pytest.raises(ValidationError):
            SearchRequest(query="valid", limit=0)

    def test_valid_chat_request(self):
        r = ChatRequest(question="What is the client's income?")
        assert r.question == "What is the client's income?"

    def test_valid_search_request(self):
        r = SearchRequest(query="tax return", limit=10)
        assert r.limit == 10


# ---------------------------------------------------------------------------
# 3. Filename sanitization
# ---------------------------------------------------------------------------


class TestFilenameSanitization:
    def test_path_traversal_slashes(self):
        assert "/" not in _sanitize_filename("../../etc/passwd")
        assert "\\" not in _sanitize_filename("..\\..\\secret.txt")

    def test_path_traversal_result(self):
        result = _sanitize_filename("../../etc/passwd")
        assert result == "etcpasswd"

    def test_null_bytes_removed(self):
        assert "\0" not in _sanitize_filename("file\0name.txt")

    def test_leading_dots_removed(self):
        result = _sanitize_filename(".hidden")
        assert not result.startswith(".")

    def test_control_chars_removed(self):
        result = _sanitize_filename("file\x01\x02\x7fname.txt")
        assert result == "filename.txt"

    def test_long_filename_truncated(self):
        long_name = "a" * 300 + ".pdf"
        result = _sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")

    def test_empty_becomes_unnamed(self):
        assert _sanitize_filename("") == "unnamed"

    def test_only_dots_becomes_unnamed(self):
        assert _sanitize_filename("...") == "unnamed"

    def test_only_slashes_becomes_unnamed(self):
        assert _sanitize_filename("///") == "unnamed"

    def test_normal_filename_unchanged(self):
        assert _sanitize_filename("2024-tax-return.pdf") == "2024-tax-return.pdf"


# ---------------------------------------------------------------------------
# 4. Organization schema validation
# ---------------------------------------------------------------------------


class TestOrgValidation:
    def test_org_name_too_long(self):
        with pytest.raises(ValidationError):
            OrgCreateRequest(name="x" * 300)

    def test_org_name_empty(self):
        with pytest.raises(ValidationError):
            OrgCreateRequest(name="")

    def test_invite_email_too_long(self):
        with pytest.raises(ValidationError):
            AddMemberRequest(user_email="x" * 300, role="member")

    def test_invite_role_too_long(self):
        with pytest.raises(ValidationError):
            AddMemberRequest(user_email="test@example.com", role="x" * 60)


# ---------------------------------------------------------------------------
# 5. Alerts schema validation
# ---------------------------------------------------------------------------


class TestAlertsValidation:
    def test_alert_type_too_long(self):
        with pytest.raises(ValidationError):
            DismissRequest(alert_type="x" * 101, related_id="abc")

    def test_related_id_too_long(self):
        with pytest.raises(ValidationError):
            DismissRequest(alert_type="test", related_id="x" * 101)

    def test_valid_dismiss_request(self):
        r = DismissRequest(alert_type="consent_expiring", related_id="some-uuid")
        assert r.alert_type == "consent_expiring"
