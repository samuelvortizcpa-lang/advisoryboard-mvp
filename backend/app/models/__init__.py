# Re-export all models so that:
#   - Alembic env.py can do `from app.models import *` to register metadata
#   - Application code can import from a single location

from app.models.user import User
from app.models.client_type import ClientType
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, EMBEDDING_DIM
from app.models.document_page_image import DocumentPageImage, IMAGE_EMBEDDING_DIM
from app.models.interaction import Interaction, INTERACTION_TYPES
from app.models.action_item import ActionItem
from app.models.chat_message import ChatMessage
from app.models.integration_connection import IntegrationConnection
from app.models.email_routing_rule import EmailRoutingRule
from app.models.sync_log import SyncLog
from app.models.client_brief import ClientBrief
from app.models.dismissed_alert import DismissedAlert
from app.models.token_usage import TokenUsage
from app.models.user_subscription import UserSubscription
from app.models.zoom_meeting_rule import ZoomMeetingRule
from app.models.client_consent import ClientConsent
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.client_access import ClientAccess
from app.models.client_assignment import ClientAssignment
from app.models.tax_strategy import TaxStrategy
from app.models.client_strategy_status import ClientStrategyStatus

__all__ = [
    "User",
    "ClientType",
    "Client",
    "Document",
    "DocumentChunk",
    "EMBEDDING_DIM",
    "DocumentPageImage",
    "IMAGE_EMBEDDING_DIM",
    "Interaction",
    "INTERACTION_TYPES",
    "ActionItem",
    "ChatMessage",
    "IntegrationConnection",
    "EmailRoutingRule",
    "SyncLog",
    "ClientBrief",
    "DismissedAlert",
    "TokenUsage",
    "UserSubscription",
    "ZoomMeetingRule",
    "ClientConsent",
    "Organization",
    "OrganizationMember",
    "ClientAccess",
    "ClientAssignment",
    "TaxStrategy",
    "ClientStrategyStatus",
]
