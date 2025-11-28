"""
Database models
All SQLAlchemy models should be defined here or imported here
"""

# Import Base for models to inherit from
from app.core.database import Base

# Import models here as they are created
from app.models.task import Task
from app.models.user import User
from app.models.tenant import Tenant
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.conversation import Conversation, Message
from app.models.validated_answer import ValidatedAnswer

# Export all models for easy imports
__all__ = [
    "Base",
    "Task",
    "User",
    "Tenant",
    "Document",
    "DocumentStatus",
    "DocumentChunk",
    "Conversation",
    "Message",
    "ValidatedAnswer",
]
