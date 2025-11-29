"""
DocumentChunk database model for storing text chunks and embeddings
Chunks are created from documents during processing for RAG pipeline
Reference: https://docs.sqlalchemy.org/en/20/orm/mapped_sql_expressions.html
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text, Float
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DocumentChunk(Base):
    """
    DocumentChunk model representing a text chunk from a document
    
    Documents are split into chunks for embedding generation and vector search.
    Each chunk contains:
    - Text content (extracted from PDF)
    - Page number (for citations)
    - Chunk index (position within document)
    - Embedding vector (stored as array in PostgreSQL, or in vector DB)
    
    Attributes:
        id: Primary key, UUID
        document_id: Foreign key to Document (parent document)
        tenant_id: Foreign key to Tenant (for tenant isolation)
        chunk_index: Position of chunk within document (0-based)
        page_number: Page number in original PDF (1-based, for citations)
        text: Text content of the chunk
        embedding: Vector embedding (stored as PostgreSQL array, or null if using external vector DB)
        token_count: Approximate number of tokens in chunk (for cost estimation)
        created_at: Timestamp when chunk was created
    
    Relationships:
        - document: Many-to-one relationship with Document
        - tenant: Many-to-one relationship with Tenant
    
    Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html
    """
    __tablename__ = "document_chunks"
    
    # Primary key: UUID for efficient PostgreSQL storage
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    
    # Document foreign key: Links chunk to parent document
    # CASCADE delete: if document is deleted, chunks are also deleted
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Index for fast document chunk queries
    )
    
    # Tenant foreign key: Enforces tenant isolation at database level
    # All queries must filter by tenant_id to prevent cross-tenant data access
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#many-to-one
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Index for fast tenant-scoped queries
    )
    
    # Chunk metadata: Position and page information
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,  # Index for ordering chunks within document
        comment="Position of chunk within document (0-based)",
    )
    
    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,  # Index for page-based queries
        comment="Page number in original PDF (1-based, for citations)",
    )
    
    # Text content: The actual chunk text
    # Using Text type for long chunks (no length limit)
    # Reference: https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Text
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    
    # Embedding vector: Stored as PostgreSQL array
    # Format: [0.123, -0.456, ...] (array of floats)
    # If using external vector DB (Qdrant/Pinecone), this can be null
    # Reference: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.ARRAY
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        ARRAY(Float),  # PostgreSQL array of floats
        nullable=True,
        comment="Vector embedding (null if using external vector DB)",
    )
    
    # Token count: Approximate number of tokens (for cost estimation)
    # Used to estimate embedding/LLM costs
    token_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Approximate number of tokens in chunk",
    )
    
    # Timestamp: When chunk was created
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,  # Index for sorting by creation time
    )
    
    # Relationships: Many-to-one with Document and Tenant
    # Using string references to avoid circular imports
    # Reference: https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#lazy-loading
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="document_chunks")
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index}, page={self.page_number}, text='{text_preview}')>"

