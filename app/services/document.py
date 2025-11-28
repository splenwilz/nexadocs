"""
Document service for file storage and metadata management
Handles document upload, storage, and database operations
Reference: https://fastapi.tiangolo.com/tutorial/request-files/
"""
import uuid
import logging
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import UploadFile, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import get_storage_backend, StorageBackend
from app.models.document import Document, DocumentStatus
from app.models.tenant import Tenant
from app.services.vector_db import VectorDBService

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Service class for document-related business logic.
    Handles file storage, validation, and database operations.
    """

    def __init__(self):
        """Initialize document service with storage configuration"""
        self.storage: StorageBackend = get_storage_backend()
        self.vector_db = VectorDBService()
        self.max_file_size = settings.MAX_FILE_SIZE
        self.allowed_mime_types = settings.allowed_mime_types_list

    async def validate_file(self, file: UploadFile) -> None:
        """
        Validate uploaded file before processing.
        
        Checks:
        - File size (must be <= MAX_FILE_SIZE)
        - MIME type (must be in ALLOWED_MIME_TYPES)
        - File is not empty
        
        Args:
            file: FastAPI UploadFile object
        
        Raises:
            HTTPException: 400 if validation fails
        """
        # Check file size
        # Read file content to get size (for small files)
        # For large files, we'd need to stream and check size
        # Reference: https://fastapi.tiangolo.com/tutorial/request-files/
        content = await file.read()
        file_size = len(content)
        
        # Reset file pointer for later reading
        await file.seek(0)
        
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty"
            )
        
        if file_size > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds maximum allowed size ({max_mb} MB)"
            )
        
        # Check MIME type
        # Use content_type from UploadFile, fallback to checking file extension
        mime_type = file.content_type
        if mime_type and mime_type not in self.allowed_mime_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{mime_type}' is not allowed. Allowed types: {', '.join(self.allowed_mime_types)}"
            )
        
        # Additional validation: Check file extension matches MIME type
        # This is a security measure to prevent MIME type spoofing
        filename = file.filename or ""
        if filename:
            ext = Path(filename).suffix.lower()
            # Map common extensions to MIME types
            ext_to_mime = {
                ".pdf": "application/pdf",
            }
            if ext in ext_to_mime and mime_type != ext_to_mime[ext]:
                logger.warning(
                    f"MIME type mismatch: filename extension '{ext}' suggests '{ext_to_mime[ext]}', "
                    f"but content_type is '{mime_type}'"
                )

    async def save_file(
        self,
        file: UploadFile,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> str:
        """
        Save uploaded file using the configured storage backend.
        
        Args:
            file: FastAPI UploadFile object
            tenant_id: UUID of the tenant
            document_id: UUID of the document
        
        Returns:
            str: Storage path/key (for database storage)
        
        Raises:
            HTTPException: 500 if file save fails
        """
        try:
            # Use storage backend to save file
            storage_path = await self.storage.save_file(file, tenant_id, document_id)
            logger.info(f"Saved file to S3: {storage_path}")
            return storage_path
        
        except Exception as e:
            logger.error(f"Failed to save file: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
            ) from e

    async def create_document(
        self,
        db: AsyncSession,
        tenant: Tenant,
        file: UploadFile,
    ) -> Document:
        """
        Create a new document record and save the file.
        
        This is the main entry point for document uploads.
        It validates the file, saves it to storage, and creates a database record.
        
        Args:
            db: Database session
            tenant: Tenant object (for tenant isolation)
            file: FastAPI UploadFile object
        
        Returns:
            Document: Created document object
        
        Raises:
            HTTPException: 400 if validation fails, 500 if save fails
        """
        create_start = time.time()
        
        # Validate file before processing
        validate_start = time.time()
        await self.validate_file(file)
        validate_time = time.time() - validate_start
        print(f"[PERF] Document validation: {validate_time:.3f}s")
        
        # Generate document ID
        document_id = uuid.uuid4()
        
        # Get file metadata
        read_start = time.time()
        content = await file.read()
        file_size = len(content)
        await file.seek(0)  # Reset for saving
        read_time = time.time() - read_start
        print(f"[PERF] File read: {read_time:.3f}s ({file_size / 1024:.2f} KB)")
        
        mime_type = file.content_type or "application/pdf"
        filename = file.filename or "document.pdf"
        
        # Save file to S3
        save_start = time.time()
        file_path = await self.save_file(file, tenant.id, document_id)
        save_time = time.time() - save_start
        print(f"[PERF] S3 upload: {save_time:.3f}s")
        
        # Create document record
        db_create_start = time.time()
        document = Document(
            id=document_id,
            tenant_id=tenant.id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            status=DocumentStatus.PENDING,  # Initial status: pending processing
        )
        
        db.add(document)
        await db.flush()  # Flush to get ID without committing
        db_create_time = time.time() - db_create_start
        print(f"[PERF] DB create document: {db_create_time:.3f}s")
        
        total_time = time.time() - create_start
        print(f"[PERF] Total create_document: {total_time:.3f}s (validate: {validate_time:.3f}s, read: {read_time:.3f}s, s3: {save_time:.3f}s, db: {db_create_time:.3f}s)")
        logger.info(f"[PERF] Created document: {document.id} for tenant: {tenant.id} ({tenant.slug}) - Total: {total_time:.3f}s")
        return document

    async def get_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Optional[Document]:
        """
        Retrieve a document by ID (tenant-scoped).
        
        Args:
            db: Database session
            document_id: UUID of the document
            tenant_id: UUID of the tenant (for isolation)
        
        Returns:
            Document if found and belongs to tenant, None otherwise
        """
        result = await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,  # Enforce tenant isolation
            )
        )
        return result.scalar_one_or_none()

    async def get_documents(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        status_filter: Optional[DocumentStatus] = None,
    ) -> List[Document]:
        """
        Retrieve a list of documents for a tenant (tenant-scoped).
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant (for isolation)
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return (pagination)
            status_filter: Optional status filter
        
        Returns:
            List of Document objects
        """
        query = select(Document).where(Document.tenant_id == tenant_id)
        
        # Apply status filter if provided
        if status_filter:
            query = query.where(Document.status == status_filter)
        
        # Apply pagination
        query = query.offset(skip).limit(limit).order_by(Document.created_at.desc())
        
        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_document_status(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        status: DocumentStatus,
        error_message: Optional[str] = None,
        page_count: Optional[int] = None,
        chunk_count: Optional[int] = None,
    ) -> Optional[Document]:
        """
        Update document processing status.
        
        Used by the document processing pipeline to update status.
        
        Args:
            db: Database session
            document_id: UUID of the document
            tenant_id: UUID of the tenant (for isolation)
            status: New processing status
            error_message: Error message if status is FAILED
            page_count: Number of pages extracted (if processing completed)
            chunk_count: Number of chunks created (if processing completed)
        
        Returns:
            Updated Document if found, None otherwise
        """
        document = await self.get_document(db, document_id, tenant_id)
        if not document:
            return None
        
        document.status = status
        if error_message:
            document.error_message = error_message
        if page_count is not None:
            document.page_count = page_count
        if chunk_count is not None:
            document.chunk_count = chunk_count
        
        # Set processed_at timestamp if status is COMPLETED or FAILED
        if status in (DocumentStatus.COMPLETED, DocumentStatus.FAILED):
            document.processed_at = datetime.now(timezone.utc)
        
        await db.flush()
        logger.info(f"Updated document {document_id} status to {status.value}")
        return document

    async def delete_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> bool:
        """
        Delete a document and its file (tenant-scoped).
        
        This performs a hard delete:
        - Removes the file from S3
        - Deletes chunks from Qdrant vector DB
        - Deletes the database record (cascade handled by DB for chunks)
        
        Args:
            db: Database session
            document_id: UUID of the document
            tenant_id: UUID of the tenant (for isolation)
        
        Returns:
            True if document was deleted, False if not found
        """
        document = await self.get_document(db, document_id, tenant_id)
        if not document:
            return False
        
        # Delete chunks from Qdrant vector DB
        try:
            await self.vector_db.delete_document_chunks(tenant_id, document_id)
            logger.info(f"Deleted chunks from Qdrant for document: {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete chunks from Qdrant: {e}", exc_info=True)
            # Continue with other deletions even if Qdrant deletion fails
        
        # Delete file from storage backend
        try:
            deleted = await self.storage.delete_file(document.file_path)
            if deleted:
                logger.info(f"Deleted file from S3: {document.file_path}")
            else:
                logger.warning(f"File not found in storage: {document.file_path}")
        except Exception as e:
            logger.error(f"Failed to delete file from storage: {e}", exc_info=True)
            # Continue with DB deletion even if file deletion fails
        
        # Delete database record
        # Note: DocumentChunks will be cascade deleted by database foreign key
        await db.delete(document)
        logger.info(f"Deleted document: {document_id}")
        return True

