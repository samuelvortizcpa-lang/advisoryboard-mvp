"""
Deliverable handler registry.

Each deliverable type (kickoff_memo, progress_note, etc.) registers a handler
that knows how to build prompts, extract references, and extract open items.
"""
from ._base import DeliverableHandler
from .kickoff_memo import KICKOFF_MEMO_HANDLER

DELIVERABLE_HANDLERS: dict[str, DeliverableHandler] = {
    "kickoff_memo": KICKOFF_MEMO_HANDLER,
}


def get_handler(deliverable_key: str) -> DeliverableHandler:
    """Look up a deliverable handler by key. Raises ValueError if unknown."""
    if deliverable_key not in DELIVERABLE_HANDLERS:
        raise ValueError(
            f"No handler registered for deliverable_key={deliverable_key!r}"
        )
    return DELIVERABLE_HANDLERS[deliverable_key]
