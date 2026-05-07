"""
Base types for the deliverable handler registry.

Each deliverable (kickoff_memo, progress_note, etc.) registers a handler
here with its prompt-builder, reference-extractor, and open-items extractor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import UUID

from app.schemas.communication import OpenItem


@dataclass(frozen=True)
class ContextBundle:
    """Assembled context slices relevant to a deliverable draft."""

    strategies: list[dict]
    action_items: list[dict]
    journal: list[dict]
    financials: dict
    comms: list[dict]


@dataclass(frozen=True)
class ClientFacts:
    """Minimal client identity for prompt construction."""

    name: str
    entity_type: str | None
    tax_year: int


@dataclass(frozen=True)
class DeliverableHandler:
    """Registry entry for a single deliverable type."""

    deliverable_key: str
    context_purpose: str
    thread_type: str
    build_prompt: Callable[[ContextBundle, ClientFacts], str]
    extract_references: Callable[[ContextBundle, ClientFacts], dict]
    extract_open_items: Callable[[str, UUID, datetime], list[OpenItem]] | None
