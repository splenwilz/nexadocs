"""
ValidatedAnswer model for storing admin-corrected answers
Allows admins to review and correct AI responses, creating validated examples
Reference: https://docs.sqlalchemy.org/en/20/orm/mapped_sql_expressions.html
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ValidatedAnswer(Base):
    """
    ValidatedAnswer model for storing admin-corrected AI responses
    
    When admins review conversations and correct an AI answer, a ValidatedAnswer
    is created. This serves as a training example and can be used to improve
    future responses or as a direct answer for similar questions.
    
    Attributes:
        id: Primary key, UUID
        tenant_id: Foreign key to Tenant (enforces tenant isolation)
        message_id: Foreign key to Message (the corrected message)
        original_question: The user's question that prompted the response
        original_answer: The original AI-generated answer (before correction)
        corrected_answer: The admin-corrected answer
        admin_notes: Optional notes explaining the correction
        created_at: Timestamp when validation was created
        updated_at: Timestamp when validation was last updated
    
    Relationships:
        - tenant: Many-to-one relationship with Tenant
        - message: Many-to-one relationship with Message
    
    Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html
    """
    __tablename__ = "validated_answers"
    
    # Primary key: UUID for efficient PostgreSQL storage
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    
    # Tenant foreign key: Enforces tenant isolation
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Index for fast tenant-scoped queries
    )
    
    # Message foreign key: Links to the corrected message
    # Allows tracking which message was corrected
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),  # Delete validation if message is deleted
        nullable=False,
        unique=True,  # One validation per message
        index=True,
    )
    
    # Original question: The user's question that prompted the response
    # Stored for context and potential future matching
    original_question: Mapped[str] = mapped_column(
        Text,  # No length limit for questions
        nullable=False,
        index=True,  # Index for semantic search (future enhancement)
    )
    
    # Original answer: The AI-generated answer before correction
    # Stored for comparison and learning purposes
    original_answer: Mapped[str] = mapped_column(
        Text,  # No length limit for answers
        nullable=False,
    )
    
    # Corrected answer: The admin-provided correct answer
    # This is the validated answer that should be used for similar questions
    corrected_answer: Mapped[str] = mapped_column(
        Text,  # No length limit for answers
        nullable=False,
    )
    
    # Admin notes: Optional explanation of why the correction was made
    # Helps understand common mistakes and improve the system
    admin_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional notes explaining the correction",
    )
    
    # Timestamps: Track validation lifecycle
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,  # Index for sorting by creation time
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
    # Relationships: Many-to-one with Tenant and Message
    # Using string references to avoid circular imports
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#lazy-loading
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="validated_answers")
    message: Mapped["Message"] = relationship("Message", back_populates="validated_answer", uselist=False)
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        question_preview = self.original_question[:50] + "..." if len(self.original_question) > 50 else self.original_question
        return f"<ValidatedAnswer(id={self.id}, tenant_id={self.tenant_id}, question='{question_preview}')>"

