"""
Document database model for storing uploaded PDF files and metadata
Documents are tenant-scoped and processed for RAG pipeline
Reference: https://docs.sqlalchemy.org/en/20/orm/mapped_sql_expressions.html
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DocumentStatus(PyEnum):
    """
    Document processing status enum
    Tracks the state of document processing pipeline
    
    Values:
        PENDING: Document uploaded but not yet processed
        PROCESSING: Currently being processed (text extraction, chunking, embeddings)
        COMPLETED: Successfully processed and ready for RAG queries
        FAILED: Processing failed (e.g., corrupted PDF, OCR failure)
    
    Reference: https://docs.python.org/3/library/enum.html
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    """
    Document model representing uploaded PDF files per tenant
    
    Documents are tenant-scoped and go through a processing pipeline:
    1. Upload → PENDING
    2. Text extraction & chunking → PROCESSING
    3. Embedding generation → PROCESSING
    4. Vector DB storage → COMPLETED
    
    Attributes:
        id: Primary key, UUID
        tenant_id: Foreign key to Tenant (enforces tenant isolation)
        filename: Original filename as uploaded by user
        file_path: S3 key (storage path)
        file_size: File size in bytes
        mime_type: MIME type (typically "application/pdf")
        status: Processing status (enum: PENDING, PROCESSING, COMPLETED, FAILED)
        error_message: Error details if status is FAILED
        page_count: Number of pages extracted (null until processing)
        chunk_count: Number of text chunks created (null until processing)
        created_at: Timestamp when document was uploaded
        updated_at: Timestamp when document was last updated
        processed_at: Timestamp when processing completed (null if not completed)
    
    Relationships:
        - tenant: Many-to-one relationship with Tenant
    
    Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html
    """
    __tablename__ = "documents"
    
    # Primary key: UUID for efficient PostgreSQL storage
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    
    # Tenant foreign key: Enforces tenant isolation at database level
    # All queries must filter by tenant_id to prevent cross-tenant data access
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#many-to-one
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),  # Delete documents when tenant is deleted
        nullable=False,
        index=True,  # Index for fast tenant-scoped queries
    )
    
    # Original filename: Preserve user's original filename
    # Not unique - multiple tenants can have files with same name
    filename: Mapped[str] = mapped_column(
        String(500),  # Support long filenames
        nullable=False,
        index=True,  # Index for search/filtering
    )
    
    # Storage path: S3 key
    # Format: tenants/{tenant_id}/documents/{document_id}.pdf
    # This ensures tenant isolation at storage level
    file_path: Mapped[str] = mapped_column(
        String(1000),  # Support long paths
        nullable=False,
        unique=True,  # Ensure no duplicate storage paths
        index=True,
    )
    
    # File metadata: Size and MIME type for validation and display
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )
    
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="application/pdf",  # Default to PDF, but allow other types
    )
    
    # Processing status: Track document processing pipeline state
    # Using Enum for type safety and database constraint
    # Reference: https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Enum
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False),  # Store as VARCHAR (more portable)
        nullable=False,
        default=DocumentStatus.PENDING,
        index=True,  # Index for filtering by status
    )
    
    # Error tracking: Store error message if processing fails
    # Allows admins to see why processing failed
    error_message: Mapped[Optional[str]] = mapped_column(
        String(2000),  # Long enough for detailed error messages
        nullable=True,
    )
    
    # Processing metrics: Track extraction results
    # These are null until processing completes
    page_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of pages extracted from PDF",
    )
    
    chunk_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of text chunks created for embeddings",
    )
    
    # Timestamps: Track document lifecycle
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
    # Processing completion timestamp: Track when processing finished
    # Null until status is COMPLETED or FAILED
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships: Many-to-one with Tenant, One-to-many with DocumentChunk
    # Using string references to avoid circular imports
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#lazy-loading
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",  # Order chunks by index
    )
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"<Document(id={self.id}, filename='{self.filename}', status={self.status.value}, tenant_id={self.tenant_id})>"

