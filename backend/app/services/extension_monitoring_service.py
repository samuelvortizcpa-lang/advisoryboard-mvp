"""Extension monitoring rules — CRUD and pattern matching."""

from __future__ import annotations

import fnmatch
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.extension_monitoring_rule import ExtensionMonitoringRule

logger = logging.getLogger(__name__)

VALID_RULE_TYPES = {"domain", "email_sender", "url_pattern", "page_content"}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_active_rules(user_id: str, db: Session) -> list[dict]:
    """Return all active rules for the user with client names."""
    rows = (
        db.query(ExtensionMonitoringRule, Client.name)
        .join(Client, ExtensionMonitoringRule.client_id == Client.id)
        .filter(
            ExtensionMonitoringRule.user_id == user_id,
            ExtensionMonitoringRule.is_active.is_(True),
        )
        .order_by(ExtensionMonitoringRule.created_at.desc())
        .all()
    )

    return [
        {
            "id": rule.id,
            "rule_name": rule.rule_name,
            "rule_type": rule.rule_type,
            "pattern": rule.pattern,
            "client_id": rule.client_id,
            "client_name": client_name,
            "is_active": rule.is_active,
            "notify_only": rule.notify_only,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        }
        for rule, client_name in rows
    ]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_rule(
    user_id: str,
    org_id: UUID | None,
    rule_data: dict[str, Any],
    db: Session,
) -> ExtensionMonitoringRule:
    """Create a monitoring rule after validating ownership and rule_type."""
    rule_type = rule_data.get("rule_type", "")
    if rule_type not in VALID_RULE_TYPES:
        raise ValueError(f"Invalid rule_type. Must be one of: {', '.join(sorted(VALID_RULE_TYPES))}")

    client_id = rule_data["client_id"]

    # Verify client belongs to the user's org
    client_q = db.query(Client).filter(Client.id == client_id)
    if org_id:
        client_q = client_q.filter(Client.org_id == org_id)
    client = client_q.first()
    if client is None:
        raise ValueError("Client not found or not accessible")

    rule = ExtensionMonitoringRule(
        user_id=user_id,
        org_id=org_id,
        rule_name=rule_data["rule_name"],
        rule_type=rule_type,
        pattern=rule_data["pattern"],
        client_id=client_id,
        notify_only=rule_data.get("notify_only", True),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def update_rule(
    rule_id: UUID,
    user_id: str,
    updates: dict[str, Any],
    db: Session,
) -> ExtensionMonitoringRule:
    """Update an existing rule (ownership check)."""
    rule = (
        db.query(ExtensionMonitoringRule)
        .filter(
            ExtensionMonitoringRule.id == rule_id,
            ExtensionMonitoringRule.user_id == user_id,
        )
        .first()
    )
    if rule is None:
        raise ValueError("Rule not found")

    allowed_fields = {"rule_name", "rule_type", "pattern", "client_id", "notify_only", "is_active"}
    for key, value in updates.items():
        if key in allowed_fields:
            if key == "rule_type" and value not in VALID_RULE_TYPES:
                raise ValueError(f"Invalid rule_type. Must be one of: {', '.join(sorted(VALID_RULE_TYPES))}")
            setattr(rule, key, value)

    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------


def delete_rule(rule_id: UUID, user_id: str, db: Session) -> None:
    """Soft-delete a rule by setting is_active=False."""
    rule = (
        db.query(ExtensionMonitoringRule)
        .filter(
            ExtensionMonitoringRule.id == rule_id,
            ExtensionMonitoringRule.user_id == user_id,
        )
        .first()
    )
    if rule is None:
        raise ValueError("Rule not found")

    rule.is_active = False
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------


def match_page_against_rules(
    user_id: str,
    page_data: dict[str, Any],
    db: Session,
) -> list[dict]:
    """
    Check page data against all active rules for the user.

    page_data keys:
      - url: str
      - domain: str
      - email_addresses: list[str] (optional)
      - page_text_snippet: str (optional)

    Returns list of matches with rule and client info.
    """
    rules = (
        db.query(ExtensionMonitoringRule, Client.name)
        .join(Client, ExtensionMonitoringRule.client_id == Client.id)
        .filter(
            ExtensionMonitoringRule.user_id == user_id,
            ExtensionMonitoringRule.is_active.is_(True),
        )
        .all()
    )

    url = page_data.get("url", "")
    domain = page_data.get("domain", "")
    emails = [e.lower() for e in page_data.get("email_addresses", [])]
    text_snippet = page_data.get("page_text_snippet", "")

    matches: list[dict] = []

    for rule, client_name in rules:
        pattern = rule.pattern
        matched = False

        if rule.rule_type == "domain":
            matched = _match_domain(pattern, domain)
        elif rule.rule_type == "email_sender":
            matched = _match_email(pattern, emails)
        elif rule.rule_type == "url_pattern":
            matched = _match_url_pattern(pattern, url)
        elif rule.rule_type == "page_content":
            matched = _match_page_content(pattern, text_snippet)

        if matched:
            matches.append({
                "rule_id": rule.id,
                "rule_name": rule.rule_name,
                "client_id": rule.client_id,
                "client_name": client_name,
                "match_type": rule.rule_type,
                "pattern_matched": pattern,
            })

    return matches


# ---------------------------------------------------------------------------
# Match helpers
# ---------------------------------------------------------------------------


def _match_domain(pattern: str, domain: str) -> bool:
    """Match domain: exact or subdomain match."""
    pattern = pattern.lower().strip()
    domain = domain.lower().strip()
    if not domain:
        return False
    return domain == pattern or domain.endswith("." + pattern)


def _match_email(pattern: str, emails: list[str]) -> bool:
    """Match email: exact address or @domain pattern."""
    pattern = pattern.lower().strip()
    for email in emails:
        if pattern.startswith("@"):
            if email.endswith(pattern):
                return True
        elif email == pattern:
            return True
    return False


def _match_url_pattern(pattern: str, url: str) -> bool:
    """Match URL using fnmatch-style glob patterns."""
    if not url:
        return False
    return fnmatch.fnmatch(url.lower(), pattern.lower())


def _match_page_content(pattern: str, text: str) -> bool:
    """Case-insensitive substring or regex match against page text."""
    if not text:
        return False
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        # Fall back to plain substring match if pattern is invalid regex
        return pattern.lower() in text.lower()
