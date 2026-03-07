# Re-export all models so that:
#   - Alembic env.py can do `from app.models import *` to register metadata
#   - Application code can import from a single location

from app.models.user import User
from app.models.client_type import ClientType
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, EMBEDDING_DIM
from app.models.interaction import Interaction, INTERACTION_TYPES
from app.models.action_item import ActionItem
from app.models.chat_message import ChatMessage
from app.models.integration_connection import IntegrationConnection
from app.models.email_routing_rule import EmailRoutingRule
from app.models.sync_log import SyncLog

__all__ = [
    "User",
    "ClientType",
    "Client",
    "Document",
    "DocumentChunk",
    "EMBEDDING_DIM",
    "Interaction",
    "INTERACTION_TYPES",
    "ActionItem",
    "ChatMessage",
    "IntegrationConnection",
    "EmailRoutingRule",
    "SyncLog",
]
