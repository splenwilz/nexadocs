from datetime import datetime
from typing import Optional
import uuid
from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class User(Base):
    """
    User model representing a user in the database
    
    Users are associated with a tenant for multi-tenant isolation.
    User IDs are strings (WorkOS format), not UUIDs.
    
    Attributes:
        id: Primary key, String (WorkOS user ID format)
        tenant_id: Foreign key to Tenant (enforces tenant isolation)
        email: User email (required, unique per tenant)
        first_name: User first name (optional)
        last_name: User last name (optional)
        created_at: Timestamp when user was created (auto-generated)
        updated_at: Timestamp when user was last updated (auto-generated)

    Reference: https://docs.sqlalchemy.org/en/20/orm/mapped_sql_expressions.html
    """
    __tablename__ = "users"

    # Primary key: String to match WorkOS user ID format
    # WorkOS user IDs are strings, not UUIDs
    # Reference: WorkOS user management API returns string IDs
    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        index=True,
    )
    
    # Tenant foreign key: Enforces tenant isolation
    # Users belong to a specific tenant and can only access their tenant's data
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#many-to-one
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),  # Delete users when tenant is deleted
        nullable=False,
        index=True,  # Index for fast tenant-scoped queries
    )
    
    # Email: Unique per tenant (not globally unique)
    # Multiple tenants can have users with same email
    # Using composite unique constraint would require separate migration
    email: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,  # Index for email lookups
    )
    
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # pending_verification_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Server-side default for creation time
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Server-side default for initial value
        onupdate=func.now(),  # Update on modification
        nullable=False,
    )

    # Relationship: Many-to-one with Tenant
    # Using string reference to avoid circular import
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#lazy-loading
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"<User(id={self.id}, email='{self.email}', tenant_id={self.tenant_id}, created_at={self.created_at})>"