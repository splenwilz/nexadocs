"""
Tenant database model for multi-tenant architecture
Each tenant represents a separate client organization with isolated data
Reference: https://docs.sqlalchemy.org/en/20/orm/mapped_sql_expressions.html
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tenant(Base):
    """
    Tenant model representing a client organization in the multi-tenant system
    
    Each tenant has isolated data - documents, conversations, and users are
    scoped to a specific tenant_id. This ensures strict data separation.
    
    Attributes:
        id: Primary key, UUID (PostgreSQL UUID type for efficiency)
        name: Human-readable tenant name (e.g., "Acme Corporation")
        slug: URL-friendly identifier (e.g., "acme-corp") - unique, indexed
        is_active: Soft delete flag - inactive tenants cannot access system
        created_at: Timestamp when tenant was created (auto-generated)
        updated_at: Timestamp when tenant was last updated (auto-generated)
    
    Relationships:
        - users: One-to-many relationship with User model
        - documents: One-to-many relationship with Document model
        - conversations: One-to-many relationship with Conversation model
    
    Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html
    """
    __tablename__ = "tenants"
    
    # Primary key: UUID type for PostgreSQL (more efficient than String)
    # Using UUID type allows PostgreSQL to optimize storage and indexing
    # Reference: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#uuid-data-type
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,  # Auto-generate UUID on insert
        nullable=False,
        index=True,  # Index for faster lookups
    )
    
    # Tenant name: Human-readable identifier
    # Not unique to allow multiple tenants with same name (different slugs)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,  # Index for search/filtering operations
    )
    
    # Slug: URL-friendly unique identifier (e.g., "acme-corp")
    # Used for subdomain routing or URL paths
    # Must be unique across all tenants
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,  # Enforce uniqueness at database level
        nullable=False,
        index=True,  # Index for fast tenant lookup by slug
    )
    
    # WorkOS organization ID: Maps WorkOS organization to our tenant
    # This allows us to link WorkOS organizations (from JWT) to our tenant model
    # Format: "org_01E4ZCR3C56J083X43JQXF3JK5" (WorkOS format)
    # Reference: https://workos.com/docs/reference/user-management/organization-memberships
    workos_organization_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,  # One tenant per WorkOS organization
        index=True,  # Index for fast lookup by WorkOS organization ID
        comment="WorkOS organization ID that maps to this tenant",
    )
    
    # Soft delete flag: Inactive tenants cannot access the system
    # Allows data retention while preventing access
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,  # New tenants are active by default
        nullable=False,
        index=True,  # Index for filtering active tenants
    )
    
    # Timestamps: Track creation and modification times
    # Using server_default ensures timestamps are set by PostgreSQL
    # This is more reliable than application-level defaults
    # Reference: https://docs.sqlalchemy.org/en/20/core/defaults.html#server-side-defaults
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # PostgreSQL CURRENT_TIMESTAMP
        nullable=False,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Initial value on insert
        onupdate=func.now(),  # Auto-update on row modification
        nullable=False,
    )
    
    # Relationships: One-to-many with related models
    # Using string references to avoid circular imports
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#lazy-loading
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="tenant")
    document_chunks: Mapped[list["DocumentChunk"]] = relationship("DocumentChunk", back_populates="tenant")
    conversations: Mapped[list["Conversation"]] = relationship("Conversation", back_populates="tenant")
    validated_answers: Mapped[list["ValidatedAnswer"]] = relationship("ValidatedAnswer", back_populates="tenant")
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"<Tenant(id={self.id}, name='{self.name}', slug='{self.slug}', is_active={self.is_active})>"

