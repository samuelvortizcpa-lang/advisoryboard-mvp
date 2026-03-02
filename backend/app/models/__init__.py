# Re-export all models so that:
#   - Alembic env.py can do `from app.models import *` to register metadata
#   - Application code can import from a single location

from app.models.user import User
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, EMBEDDING_DIM
from app.models.interaction import Interaction, INTERACTION_TYPES

__all__ = [
    "User",
    "Client",
    "Document",
    "DocumentChunk",
    "EMBEDDING_DIM",
    "Interaction",
    "INTERACTION_TYPES",
]
