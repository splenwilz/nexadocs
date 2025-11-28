"""
Document API schemas for request/response models
Reference: https://fastapi.tiangolo.com/tutorial/body/
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    """
    Schema for document response
    
    Includes all document fields returned from the API.
    Used for GET endpoints.
    
    Attributes:
        id: Document UUID
        tenant_id: Tenant UUID (for tenant isolation)
        filename: Original filename
        file_path: Storage path
        file_size: File size in bytes
        mime_type: MIME type (typically "application/pdf")
        status: Processing status (enum)
        error_message: Error details if processing failed
        page_count: Number of pages extracted
        chunk_count: Number of text chunks created
        created_at: Timestamp when document was uploaded
        updated_at: Timestamp when document was last updated
        processed_at: Timestamp when processing completed
    
    Reference: https://fastapi.tiangolo.com/tutorial/response-model/
    """
    id: uuid.UUID = Field(..., description="Document UUID")
    tenant_id: uuid.UUID = Field(..., description="Tenant UUID")
    filename: str = Field(..., description="Original filename")
    file_path: str = Field(..., description="Storage path")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    status: DocumentStatus = Field(..., description="Processing status")
    error_message: Optional[str] = Field(None, description="Error message if processing failed")
    page_count: Optional[int] = Field(None, description="Number of pages extracted")
    chunk_count: Optional[int] = Field(None, description="Number of text chunks created")
    created_at: datetime = Field(..., description="Timestamp when document was uploaded")
    updated_at: datetime = Field(..., description="Timestamp when document was last updated")
    processed_at: Optional[datetime] = Field(None, description="Timestamp when processing completed")
    
    # Enable Pydantic to read from SQLAlchemy models
    # Reference: https://docs.pydantic.dev/latest/concepts/models/#orm-mode-aka-arbitrary-class-instances
    model_config = ConfigDict(from_attributes=True)


class DocumentUpdate(BaseModel):
    """
    Schema for updating document metadata (admin only)
    
    Currently limited - most document updates happen through processing pipeline.
    This is mainly for admin corrections or status updates.
    
    Attributes:
        status: Update processing status (optional)
        error_message: Update error message (optional)
    
    Reference: https://fastapi.tiangolo.com/tutorial/body/
    """
    status: Optional[DocumentStatus] = Field(None, description="Processing status")
    error_message: Optional[str] = Field(None, description="Error message")

