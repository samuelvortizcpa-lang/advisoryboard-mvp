"""
Security regression tests — rate limiting and enumeration protection (H4).

Verifies that the consent signing endpoint blocks IPs after too many
failed token lookups (anti-enumeration).
"""

import time

import pytest

from app.api.consent_public import (
    _check_enumeration_block,
    _failed_lookups,
    _record_failed_lookup,
    _FAILED_MAX,
)
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def clear_failed_lookups():
    """Reset the in-memory failed lookup tracker between tests."""
    _failed_lookups.clear()
    yield
    _failed_lookups.clear()


# ---------------------------------------------------------------------------
# 1. Under-limit lookups are allowed
# ---------------------------------------------------------------------------


def test_below_threshold_allowed():
    """Fewer than _FAILED_MAX failures should not trigger a block."""
    ip = "10.0.0.1"
    for _ in range(_FAILED_MAX - 1):
        _record_failed_lookup(ip)
    # Should not raise
    _check_enumeration_block(ip)


# ---------------------------------------------------------------------------
# 2. At-limit lookups trigger a block
# ---------------------------------------------------------------------------


def test_at_threshold_blocked():
    """Exactly _FAILED_MAX failures should block."""
    ip = "10.0.0.2"
    for _ in range(_FAILED_MAX):
        _record_failed_lookup(ip)

    with pytest.raises(HTTPException) as exc_info:
        _check_enumeration_block(ip)
    assert exc_info.value.status_code == 429
    assert "failed attempts" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# 3. Over-limit lookups remain blocked
# ---------------------------------------------------------------------------


def test_over_threshold_blocked():
    """More than _FAILED_MAX failures should still block."""
    ip = "10.0.0.3"
    for _ in range(_FAILED_MAX + 5):
        _record_failed_lookup(ip)

    with pytest.raises(HTTPException) as exc_info:
        _check_enumeration_block(ip)
    assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# 4. Different IPs are tracked independently
# ---------------------------------------------------------------------------


def test_different_ips_independent():
    """Failures from one IP shouldn't affect another."""
    ip_a = "10.0.0.10"
    ip_b = "10.0.0.11"

    for _ in range(_FAILED_MAX):
        _record_failed_lookup(ip_a)

    # ip_a should be blocked
    with pytest.raises(HTTPException):
        _check_enumeration_block(ip_a)

    # ip_b should be fine
    _check_enumeration_block(ip_b)


# ---------------------------------------------------------------------------
# 5. Clean IP passes without any failures
# ---------------------------------------------------------------------------


def test_clean_ip_passes():
    """An IP with no recorded failures should pass."""
    _check_enumeration_block("192.168.1.1")
