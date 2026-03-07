"""
Email routing service: matches incoming email addresses to clients
using the email_routing_rules table.

Also handles CRUD operations on routing rules and auto-generation
of rules from existing client email addresses.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.email_routing_rule import EmailRoutingRule
from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Match an email to a client
# ---------------------------------------------------------------------------


def match_email_to_client(
    from_email: str,
    to_emails: List[str],
    user_id: str,
    db: Session,
) -> Optional[UUID]:
    """
    Check email_routing_rules for a matching rule and return the client_id.

    Priority:
      1. Exact match on from_email with match_type 'from' or 'both'
      2. Exact match on any to_email with match_type 'to' or 'both'

    Returns None if no rule matches.
    """
    from_lower = from_email.strip().lower()

    # ── Try 'from' match first (higher priority) ─────────────────────────
    from_rule = (
        db.query(EmailRoutingRule)
        .filter(
            EmailRoutingRule.user_id == user_id,
            EmailRoutingRule.is_active == True,
            EmailRoutingRule.email_address == from_lower,
            EmailRoutingRule.match_type.in_(["from", "both"]),
        )
        .first()
    )
    if from_rule:
        return from_rule.client_id

    # ── Then try 'to' match ───────────────────────────────────────────────
    if to_emails:
        to_lower = [addr.strip().lower() for addr in to_emails if addr.strip()]
        if to_lower:
            to_rule = (
                db.query(EmailRoutingRule)
                .filter(
                    EmailRoutingRule.user_id == user_id,
                    EmailRoutingRule.is_active == True,
                    EmailRoutingRule.email_address.in_(to_lower),
                    EmailRoutingRule.match_type.in_(["to", "both"]),
                )
                .first()
            )
            if to_rule:
                return to_rule.client_id

    return None


# ---------------------------------------------------------------------------
# 2. Auto-create routing rules from existing client emails
# ---------------------------------------------------------------------------


def auto_create_routing_rules(user_id: str, db: Session) -> List[EmailRoutingRule]:
    """
    Scan all clients owned by the user that have an email address set
    and create a 'from' routing rule for each one that doesn't already
    have a rule.

    Returns the list of newly created rules.
    """
    # Resolve the Clerk user_id → internal User.id for the ownership query
    owner = db.query(User).filter(User.clerk_id == user_id).first()
    if not owner:
        logger.warning("auto_create_routing_rules: user %s not found", user_id)
        return []

    # Get all clients with an email address
    clients_with_email = (
        db.query(Client)
        .filter(
            Client.owner_id == owner.id,
            Client.email.isnot(None),
            Client.email != "",
        )
        .all()
    )

    if not clients_with_email:
        logger.info(
            "auto_create_routing_rules: no clients with emails for user %s",
            user_id,
        )
        return []

    # Get existing rules to avoid duplicates
    existing_rules = (
        db.query(EmailRoutingRule)
        .filter(
            EmailRoutingRule.user_id == user_id,
            EmailRoutingRule.match_type == "from",
        )
        .all()
    )
    existing_emails = {
        rule.email_address.strip().lower() for rule in existing_rules
    }

    # Create new rules
    created: list[EmailRoutingRule] = []
    for client in clients_with_email:
        email_lower = client.email.strip().lower()
        if email_lower in existing_emails:
            continue

        rule = EmailRoutingRule(
            user_id=user_id,
            email_address=email_lower,
            client_id=client.id,
            match_type="from",
        )
        db.add(rule)
        created.append(rule)
        existing_emails.add(email_lower)  # prevent duplicates within batch

    if created:
        db.commit()
        for rule in created:
            db.refresh(rule)
        logger.info(
            "auto_create_routing_rules: created %d rule(s) for user %s",
            len(created),
            user_id,
        )

    return created


# ---------------------------------------------------------------------------
# 3. List routing rules (with client names)
# ---------------------------------------------------------------------------


def get_routing_rules(user_id: str, db: Session) -> List[dict]:
    """
    Return all routing rules for the user, enriched with the client name.

    Each item is a dict with rule fields + ``client_name``.
    """
    rules = (
        db.query(EmailRoutingRule, Client.name)
        .join(Client, EmailRoutingRule.client_id == Client.id)
        .filter(EmailRoutingRule.user_id == user_id)
        .order_by(EmailRoutingRule.email_address)
        .all()
    )

    return [
        {
            "id": rule.id,
            "user_id": rule.user_id,
            "email_address": rule.email_address,
            "client_id": rule.client_id,
            "client_name": client_name,
            "match_type": rule.match_type,
            "is_active": rule.is_active,
            "created_at": rule.created_at.isoformat(),
        }
        for rule, client_name in rules
    ]


# ---------------------------------------------------------------------------
# 4. Create a routing rule
# ---------------------------------------------------------------------------


def create_routing_rule(
    user_id: str,
    email_address: str,
    client_id: UUID,
    match_type: str,
    db: Session,
) -> EmailRoutingRule:
    """
    Create a new routing rule.

    Validates:
      - match_type is one of 'from', 'to', 'both'
      - the client exists and is owned by the user
      - no duplicate rule exists

    Raises ValueError on validation failure.
    """
    # Validate match_type
    if match_type not in ("from", "to", "both"):
        raise ValueError(f"Invalid match_type: {match_type!r}. Must be 'from', 'to', or 'both'.")

    email_lower = email_address.strip().lower()
    if not email_lower or "@" not in email_lower:
        raise ValueError(f"Invalid email address: {email_address!r}")

    # Verify client ownership
    owner = db.query(User).filter(User.clerk_id == user_id).first()
    if not owner:
        raise ValueError("User not found")

    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner.id)
        .first()
    )
    if not client:
        raise ValueError(f"Client {client_id} not found or not owned by user")

    # Check for duplicate
    existing = (
        db.query(EmailRoutingRule)
        .filter(
            EmailRoutingRule.user_id == user_id,
            EmailRoutingRule.email_address == email_lower,
            EmailRoutingRule.match_type == match_type,
        )
        .first()
    )
    if existing:
        raise ValueError(
            f"A rule for {email_lower!r} with match_type={match_type!r} already exists"
        )

    rule = EmailRoutingRule(
        user_id=user_id,
        email_address=email_lower,
        client_id=client_id,
        match_type=match_type,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info(
        "Created routing rule: %s → client %s (%s, match_type=%s)",
        email_lower,
        client_id,
        client.name,
        match_type,
    )
    return rule


# ---------------------------------------------------------------------------
# 5. Delete a routing rule
# ---------------------------------------------------------------------------


def delete_routing_rule(rule_id: UUID, user_id: str, db: Session) -> bool:
    """
    Delete a routing rule (with ownership check).

    Returns True if the rule was found and deleted, False otherwise.
    """
    rule = (
        db.query(EmailRoutingRule)
        .filter(
            EmailRoutingRule.id == rule_id,
            EmailRoutingRule.user_id == user_id,
        )
        .first()
    )
    if not rule:
        return False

    db.delete(rule)
    db.commit()
    logger.info("Deleted routing rule %s for user %s", rule_id, user_id)
    return True
