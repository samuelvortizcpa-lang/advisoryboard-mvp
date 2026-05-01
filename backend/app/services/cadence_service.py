"""
Cadence service layer (Layer 2 Gap 4 — G4-P2).

8 functions covering deliverable enablement resolution, client cadence
assignment, override management, custom template CRUD, template
deactivation, and firm-default setter.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.cadence_template import CadenceTemplate
from app.models.cadence_template_deliverable import (
    CadenceTemplateDeliverable,
    DELIVERABLE_KEY_VALUES,
)
from app.models.client_cadence import ClientCadence
from app.models.organization import Organization

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. is_deliverable_enabled
# ---------------------------------------------------------------------------


def is_deliverable_enabled(
    db: Session, client_id: UUID, deliverable_key: str
) -> bool:
    """Check if a deliverable is enabled for a client, respecting overrides."""
    if deliverable_key not in DELIVERABLE_KEY_VALUES:
        raise ValueError(f"Invalid deliverable_key: {deliverable_key!r}")

    cc = (
        db.query(ClientCadence)
        .filter(ClientCadence.client_id == client_id)
        .first()
    )
    if cc is None:
        return False

    # Override wins
    overrides = cc.overrides or {}
    if deliverable_key in overrides:
        return bool(overrides[deliverable_key])

    # Fall back to template default
    row = (
        db.query(CadenceTemplateDeliverable.is_enabled)
        .filter(
            CadenceTemplateDeliverable.template_id == cc.template_id,
            CadenceTemplateDeliverable.deliverable_key == deliverable_key,
        )
        .first()
    )
    return bool(row[0]) if row else False


# ---------------------------------------------------------------------------
# 2. list_enabled_deliverables
# ---------------------------------------------------------------------------


def list_enabled_deliverables(db: Session, client_id: UUID) -> list[str]:
    """Return the list of enabled deliverable keys for a client."""
    cc = (
        db.query(ClientCadence)
        .filter(ClientCadence.client_id == client_id)
        .first()
    )
    if cc is None:
        return []

    overrides = cc.overrides or {}

    # Single query for all template deliverables
    rows = (
        db.query(
            CadenceTemplateDeliverable.deliverable_key,
            CadenceTemplateDeliverable.is_enabled,
        )
        .filter(CadenceTemplateDeliverable.template_id == cc.template_id)
        .all()
    )
    template_map = {r[0]: r[1] for r in rows}

    enabled = []
    for key in DELIVERABLE_KEY_VALUES:
        if key in overrides:
            if overrides[key]:
                enabled.append(key)
        elif template_map.get(key, False):
            enabled.append(key)

    return enabled


# ---------------------------------------------------------------------------
# 3. assign_cadence
# ---------------------------------------------------------------------------


def assign_cadence(
    db: Session,
    client_id: UUID,
    template_id: UUID,
    assigned_by: str,
) -> ClientCadence:
    """Assign (or reassign) a cadence template to a client. Idempotent."""
    # Validate template
    template = (
        db.query(CadenceTemplate)
        .filter(CadenceTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise ValueError(f"Template {template_id} does not exist")
    if not template.is_active:
        raise ValueError(f"Template {template_id} is not active")

    # Check for existing assignment
    cc = (
        db.query(ClientCadence)
        .filter(ClientCadence.client_id == client_id)
        .first()
    )
    previous_template_id = cc.template_id if cc else None

    if cc is None:
        cc = ClientCadence(
            client_id=client_id,
            template_id=template_id,
            overrides={},
            assigned_by=assigned_by,
        )
        db.add(cc)
    else:
        cc.template_id = template_id
        cc.overrides = {}
        cc.assigned_by = assigned_by
        cc.updated_at = func.now()

    db.flush()

    # Journal entry — skip on same-template re-assign (true no-op for audit)
    if previous_template_id != template_id:
        try:
            from app.services.journal_service import create_auto_entry

            create_auto_entry(
                db=db,
                client_id=client_id,
                user_id=assigned_by,
                entry_type="cadence_change",
                category="cadence",
                title=f"Cadence assigned: {template.name}",
                metadata={
                    "template_id": str(template_id),
                    "template_name": template.name,
                    "previous_template_id": str(previous_template_id) if previous_template_id else None,
                },
            )
        except Exception:
            logger.warning("Journal entry for cadence assignment failed (non-fatal)", exc_info=True)

    return cc


# ---------------------------------------------------------------------------
# 4. update_overrides
# ---------------------------------------------------------------------------


def update_overrides(
    db: Session,
    client_id: UUID,
    overrides: dict[str, bool],
    updated_by: str,
) -> ClientCadence:
    """Merge override flags into the client's cadence JSONB."""
    # Validate keys
    for key in overrides:
        if key not in DELIVERABLE_KEY_VALUES:
            raise ValueError(f"Invalid deliverable_key: {key!r}")

    # Validate values are strict bool
    for key, value in overrides.items():
        if not isinstance(value, bool):
            raise ValueError(
                f"Override value for {key!r} must be bool, got {type(value).__name__}"
            )

    cc = (
        db.query(ClientCadence)
        .filter(ClientCadence.client_id == client_id)
        .first()
    )
    if cc is None:
        raise ValueError(f"No cadence assignment for client {client_id}")

    existing = cc.overrides or {}

    # Identify actually changed keys
    changed_keys = {}
    for key, new_value in overrides.items():
        old_value = existing.get(key)
        if old_value != new_value:
            changed_keys[key] = (old_value, new_value)

    # Merge: incoming keys overwrite, existing keys preserved
    merged = {**existing, **overrides}
    cc.overrides = merged
    cc.updated_at = func.now()
    db.flush()

    # One journal entry per changed key
    if changed_keys:
        try:
            from app.services.journal_service import create_auto_entry

            for key, (old_val, new_val) in changed_keys.items():
                label = key.replace("_", " ").title()
                action = "enabled" if new_val else "disabled"
                create_auto_entry(
                    db=db,
                    client_id=client_id,
                    user_id=updated_by,
                    entry_type="cadence_override",
                    category="cadence",
                    title=f"Deliverable override: {label} {action}",
                    metadata={
                        "deliverable_key": key,
                        "old_value": old_val,
                        "new_value": new_val,
                    },
                )
        except Exception:
            logger.warning("Journal entries for cadence overrides failed (non-fatal)", exc_info=True)

    return cc


# ---------------------------------------------------------------------------
# 5. create_custom_template
# ---------------------------------------------------------------------------


def create_custom_template(
    db: Session,
    org_id: UUID,
    name: str,
    description: Optional[str],
    deliverable_flags: dict[str, bool],
    created_by: str,
) -> CadenceTemplate:
    """Create a firm-defined cadence template with all 7 deliverable rows."""
    if org_id is None:
        raise ValueError("org_id is required for custom templates")

    # Validate all 7 keys present, no extras
    expected = set(DELIVERABLE_KEY_VALUES)
    provided = set(deliverable_flags.keys())
    if provided != expected:
        missing = expected - provided
        extra = provided - expected
        parts = []
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if extra:
            parts.append(f"extra: {sorted(extra)}")
        raise ValueError(f"deliverable_flags must contain exactly 7 keys; {', '.join(parts)}")

    template = CadenceTemplate(
        org_id=org_id,
        name=name,
        description=description,
        is_system=False,
        is_active=True,
        created_by=created_by,
    )
    db.add(template)
    db.flush()

    for key in DELIVERABLE_KEY_VALUES:
        deliverable = CadenceTemplateDeliverable(
            template_id=template.id,
            deliverable_key=key,
            is_enabled=deliverable_flags[key],
        )
        db.add(deliverable)

    db.commit()
    db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# 6. update_template
# ---------------------------------------------------------------------------


def update_template(
    db: Session,
    template_id: UUID,
    name: Optional[str],
    description: Optional[str],
    deliverable_flags: Optional[dict[str, bool]],
    updated_by: str,
) -> CadenceTemplate:
    """Update a firm-defined template. Refuses system templates."""
    template = (
        db.query(CadenceTemplate)
        .filter(CadenceTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise ValueError(f"Template {template_id} does not exist")
    if template.is_system:
        raise ValueError("Cannot modify system templates")

    if name is not None:
        template.name = name
    if description is not None:
        template.description = description

    if deliverable_flags is not None:
        # Validate keys
        for key in deliverable_flags:
            if key not in DELIVERABLE_KEY_VALUES:
                raise ValueError(f"Invalid deliverable_key: {key!r}")

        # Partial update: only change provided keys
        for key, is_enabled in deliverable_flags.items():
            row = (
                db.query(CadenceTemplateDeliverable)
                .filter(
                    CadenceTemplateDeliverable.template_id == template_id,
                    CadenceTemplateDeliverable.deliverable_key == key,
                )
                .first()
            )
            if row:
                row.is_enabled = is_enabled

    template.updated_at = func.now()
    db.commit()
    db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# 7. deactivate_template
# ---------------------------------------------------------------------------


def deactivate_template(
    db: Session, template_id: UUID, updated_by: str
) -> None:
    """Soft-deactivate a firm-defined template."""
    template = (
        db.query(CadenceTemplate)
        .filter(CadenceTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise ValueError(f"Template {template_id} does not exist")
    if template.is_system:
        raise ValueError("Cannot deactivate system templates")

    # Refuse if any client references this template
    ref_count = (
        db.query(ClientCadence)
        .filter(ClientCadence.template_id == template_id)
        .count()
    )
    if ref_count > 0:
        raise ValueError(
            f"Template {template_id} is referenced by {ref_count} client_cadence row(s); "
            "reassign clients before deactivating"
        )

    template.is_active = False
    template.updated_at = func.now()
    db.commit()


# ---------------------------------------------------------------------------
# 8. set_firm_default
# ---------------------------------------------------------------------------


def set_firm_default(
    db: Session,
    org_id: UUID,
    template_id: Optional[UUID],
    updated_by: str,
) -> None:
    """Set or clear the org's default cadence template."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise ValueError(f"Organization {org_id} does not exist")

    if template_id is None:
        org.default_cadence_template_id = None
        db.commit()
        return

    template = (
        db.query(CadenceTemplate)
        .filter(CadenceTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise ValueError(f"Template {template_id} does not exist")

    # Scope check: system templates always OK; org templates must match org_id
    if not template.is_system and template.org_id != org_id:
        raise ValueError(
            f"Template {template_id} belongs to org {template.org_id}, "
            f"not {org_id}; cross-org assignment not allowed"
        )

    org.default_cadence_template_id = template_id
    db.commit()
