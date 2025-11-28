"""
Conversation and Message models for chat functionality
Conversations are tenant-scoped chat sessions with AI assistant
Reference: https://docs.sqlalchemy.org/en/20/orm/mapped_sql_expressions.html
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Conversation(Base):
    """
    Conversation model representing a chat session between user and AI assistant
    
    Each conversation belongs to a tenant and user, containing multiple messages.
    Conversations track the chat history for context-aware responses.
    
    Attributes:
        id: Primary key, UUID
        tenant_id: Foreign key to Tenant (enforces tenant isolation)
        user_id: Foreign key to User (WorkOS user ID - string)
        title: Optional conversation title (auto-generated from first message)
        created_at: Timestamp when conversation was created
        updated_at: Timestamp when last message was added
    
    Relationships:
        - tenant: Many-to-one relationship with Tenant
        - messages: One-to-many relationship with Message
    
    Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html
    """
    __tablename__ = "conversations"
    
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
    
    # User foreign key: Links to WorkOS user
    # Using String to match WorkOS user ID format (not UUID)
    # Reference: WorkOS user IDs are strings, not UUIDs
    user_id: Mapped[str] = mapped_column(
        String,  # WorkOS user IDs are strings
        ForeignKey("users.id", ondelete="CASCADE"),  # Cascade delete if user is deleted
        nullable=False,
        index=True,  # Index for user's conversation list queries
    )
    
    # Conversation title: Optional, auto-generated from first message
    # Allows users to identify conversations in a list
    title: Mapped[Optional[str]] = mapped_column(
        String(500),  # Long enough for descriptive titles
        nullable=True,
        index=True,  # Index for search functionality
    )
    
    # Timestamps: Track conversation lifecycle
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
        index=True,  # Index for sorting by last activity
    )
    
    # Relationships: One-to-many with Message, Many-to-one with Tenant and User
    # Using string references to avoid circular imports
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#lazy-loading
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",  # Order messages by creation time
    )
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="conversations")
    user: Mapped["User"] = relationship("User", back_populates="conversations")
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"<Conversation(id={self.id}, title='{self.title}', tenant_id={self.tenant_id}, user_id={self.user_id})>"


class Message(Base):
    """
    Message model representing individual messages in a conversation
    
    Messages can be from the user (query) or from the AI assistant (response).
    AI responses include citations to source documents.
    
    Attributes:
        id: Primary key, UUID
        conversation_id: Foreign key to Conversation
        role: Message role - "user" or "assistant"
        content: Message text content
        citations: JSON string of document citations (for assistant messages)
        created_at: Timestamp when message was created
    
    Relationships:
        - conversation: Many-to-one relationship with Conversation
    
    Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html
    """
    __tablename__ = "messages"
    
    # Primary key: UUID for efficient PostgreSQL storage
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    
    # Conversation foreign key: Links message to conversation
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),  # Delete messages when conversation is deleted
        nullable=False,
        index=True,  # Index for fast conversation message queries
    )
    
    # Message role: "user" or "assistant"
    # Using String instead of Enum for simplicity (only 2 values)
    # Could be extended to Enum if more roles are needed
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,  # Index for filtering by role
        comment="Message role: 'user' or 'assistant'",
    )
    
    # Message content: The actual text of the message
    # Using Text type for long messages (no length limit)
    # Reference: https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Text
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    
    # Citations: JSON string containing document citations for assistant messages
    # Format: [{"document_id": "...", "document_name": "...", "page": 1, "chunk_index": 0}]
    # Stored as Text to support long citation lists
    # Null for user messages (only assistant messages have citations)
    citations: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON string of document citations (for assistant messages only)",
    )
    
    # Timestamp: When message was created
    # Used for ordering messages in conversation
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,  # Index for sorting messages chronologically
    )
    
    # Relationships: Many-to-one with Conversation, One-to-one with ValidatedAnswer
    # Using string references to avoid circular imports
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#lazy-loading
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    validated_answer: Mapped[Optional["ValidatedAnswer"]] = relationship(
        "ValidatedAnswer",
        back_populates="message",
        uselist=False,  # One-to-one relationship
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, role='{self.role}', conversation_id={self.conversation_id}, content='{content_preview}')>"

