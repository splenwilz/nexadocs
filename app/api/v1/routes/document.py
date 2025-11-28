"""
Document API routes for file upload and management
Handles tenant-scoped document operations
Reference: https://fastapi.tiangolo.com/tutorial/request-files/
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.document import DocumentResponse, DocumentUpdate
from app.core.database import get_db, async_session_maker
from app.core.tenant import CurrentTenant
from app.models.document import DocumentStatus, Document
from app.models.tenant import Tenant
from app.services.document import DocumentService
from app.services.document_processor import DocumentProcessor
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.post(
    "",
    response_model=DocumentResponse,
    summary="Upload document",
    description="Upload a PDF document for processing (tenant-scoped)",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(..., description="PDF file to upload"),
    tenant: CurrentTenant = ...,  # Required dependency (FastAPI injects via Depends)
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Upload a document for processing.
    
    This endpoint:
    1. Validates the file (size, MIME type)
    2. Saves the file to tenant-specific storage (S3)
    3. Creates a document record with PENDING status
    4. Triggers background processing (text extraction, chunking, embeddings)
    5. Returns the document metadata
    
    Processing happens asynchronously in the background:
    - Text extraction from PDF
    - Text chunking
    - Embedding generation
    - Database storage of chunks
    
    Args:
        file: PDF file to upload (multipart/form-data)
        tenant: Current tenant (from dependency injection)
        background_tasks: FastAPI background tasks (for async processing)
        db: Database session (from dependency injection)
    
    Returns:
        DocumentResponse: Created document metadata (status will be PENDING initially)
    
    Raises:
        HTTPException: 400 if file validation fails
        HTTPException: 500 if file save fails
    """
    import time
    start_time = time.time()
    
    document_service = DocumentService()
    
    try:
        # Create document and save file
        upload_start = time.time()
        document = await document_service.create_document(db, tenant, file)
        upload_time = time.time() - upload_start
        print(f"[PERF] Document upload & S3 save: {upload_time:.3f}s")
        logger.info(f"[PERF] Document upload & S3 save: {upload_time:.3f}s")
        
        # Commit transaction
        commit_start = time.time()
        await db.commit()
        commit_time = time.time() - commit_start
        print(f"[PERF] Database commit: {commit_time:.3f}s")
        logger.info(f"[PERF] Database commit: {commit_time:.3f}s")
        
        # Trigger background processing
        # Note: We need to create a new DB session for the background task
        # since the current session will be closed after response
        background_tasks.add_task(
            process_document_background,
            document_id=document.id,
            tenant_id=tenant.id,
        )
        
        total_time = time.time() - start_time
        print(f"[PERF] Total upload endpoint time: {total_time:.3f}s")
        logger.info(f"[PERF] Document uploaded: {document.id} for tenant: {tenant.id} ({tenant.slug}) - Total: {total_time:.3f}s")
        return DocumentResponse.model_validate(document)
    
    except HTTPException:
        # Re-raise HTTP exceptions (already formatted)
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error uploading document: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while uploading the document"
        ) from e


async def process_document_background(document_id: uuid.UUID, tenant_id: uuid.UUID, reprocess: bool = False):
    """
    Background task to process a document
    
    This function runs asynchronously after the upload response is sent.
    It processes the document through the complete pipeline:
    - Text extraction from PDF
    - Text chunking
    - Embedding generation
    - Database storage of chunks
    
    Args:
        document_id: UUID of the document to process
        tenant_id: UUID of the tenant (for security)
        reprocess: If True, delete existing chunks and reprocess
    """
    import time
    total_start = time.time()
    
    # Create new database session for background task
    async with async_session_maker() as db:
        try:
            # Get document (with tenant check for security)
            from sqlalchemy import select
            
            db_fetch_start = time.time()
            result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant_id == tenant_id,  # Security: verify tenant
                )
            )
            document = result.scalar_one_or_none()
            db_fetch_time = time.time() - db_fetch_start
            print(f"[PERF] Background: DB fetch document: {db_fetch_time:.3f}s")
            
            if not document:
                logger.error(f"Document {document_id} not found for tenant {tenant_id}")
                return
            
            # Process document
            processor = DocumentProcessor()
            process_start = time.time()
            if reprocess:
                await processor.reprocess_document(db, document)
            else:
                await processor.process_document(db, document)
            process_time = time.time() - process_start
            print(f"[PERF] Background: Document processing pipeline: {process_time:.3f}s")
            
            # Commit changes
            commit_start = time.time()
            await db.commit()
            commit_time = time.time() - commit_start
            print(f"[PERF] Background: Database commit: {commit_time:.3f}s")
            
            total_time = time.time() - total_start
            print(f"[PERF] Background: Total processing time: {total_time:.3f}s")
            logger.info(f"[PERF] Successfully processed document {document_id} in background (reprocess={reprocess}) - Total: {total_time:.3f}s")
            
        except Exception as e:
            logger.error(f"Error processing document {document_id} in background: {e}", exc_info=True)
            await db.rollback()
            # Document status should already be set to FAILED by processor


@router.get(
    "",
    response_model=List[DocumentResponse],
    summary="List documents",
    description="Get a list of documents for the current tenant",
    status_code=status.HTTP_200_OK,
)
async def list_documents(
    skip: int = Query(0, ge=0, description="Number of documents to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of documents to return"),
    status_filter: Optional[DocumentStatus] = Query(None, description="Filter by processing status"),
    tenant: CurrentTenant = ...,  # Required dependency (FastAPI injects via Depends)
    db: AsyncSession = Depends(get_db),
) -> List[DocumentResponse]:
    """
    Get a list of documents for the current tenant.
    
    Results are automatically filtered by tenant_id for security.
    Supports pagination and optional status filtering.
    
    Args:
        skip: Number of documents to skip (pagination)
        limit: Maximum number of documents to return (pagination)
        status_filter: Optional status filter (PENDING, PROCESSING, COMPLETED, FAILED)
        tenant: Current tenant (from dependency injection)
        db: Database session (from dependency injection)
    
    Returns:
        List of DocumentResponse objects
    """
    document_service = DocumentService()
    documents = await document_service.get_documents(
        db,
        tenant.id,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
    )
    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document",
    description="Get a document by ID (tenant-scoped)",
    status_code=status.HTTP_200_OK,
)
async def get_document(
    document_id: uuid.UUID,
    tenant: CurrentTenant = ...,  # Required dependency (FastAPI injects via Depends)
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Get a document by ID.
    
    Automatically enforces tenant isolation - users can only access
    documents belonging to their tenant.
    
    Args:
        document_id: UUID of the document
        tenant: Current tenant (from dependency injection)
        db: Database session (from dependency injection)
    
    Returns:
        DocumentResponse: Document metadata
    
    Raises:
        HTTPException: 404 if document not found or doesn't belong to tenant
    """
    document_service = DocumentService()
    document = await document_service.get_document(db, document_id, tenant.id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found"
        )
    
    return DocumentResponse.model_validate(document)


@router.delete(
    "/{document_id}",
    summary="Delete document",
    description="Delete a document and its file (tenant-scoped)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "Document not found"},
        204: {"description": "Document deleted successfully"},
    },
)
async def delete_document(
    document_id: uuid.UUID,
    tenant: CurrentTenant = ...,  # Required dependency (FastAPI injects via Depends)
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a document and its file.
    
    This performs a hard delete:
    - Removes the file from filesystem
    - Deletes the database record
    
    Automatically enforces tenant isolation.
    
    Args:
        document_id: UUID of the document to delete
        tenant: Current tenant (from dependency injection)
        db: Database session (from dependency injection)
    
    Returns:
        None (204 No Content)
    
    Raises:
        HTTPException: 404 if document not found or doesn't belong to tenant
    """
    document_service = DocumentService()
    
    try:
        deleted = await document_service.delete_document(db, document_id, tenant.id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        await db.commit()
        logger.info(f"Document deleted: {document_id} for tenant: {tenant.id}")
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error deleting document: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting the document"
        ) from e


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentResponse,
    summary="Reprocess document",
    description="Reprocess a document (useful for fixing failed processing or updating embeddings)",
    status_code=status.HTTP_200_OK,
)
async def reprocess_document(
    document_id: uuid.UUID,
    tenant: CurrentTenant = ...,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Reprocess a document.
    
    This endpoint:
    1. Deletes existing chunks from database and Qdrant
    2. Resets document status to PENDING
    3. Triggers background processing again
    
    Useful for:
    - Fixing processing errors
    - Updating embeddings after model change
    - Re-chunking with different settings
    
    Args:
        document_id: UUID of the document to reprocess
        tenant: Current tenant (from dependency injection)
        background_tasks: FastAPI background tasks (for async processing)
        db: Database session (from dependency injection)
    
    Returns:
        DocumentResponse: Document metadata (status will be PENDING initially)
    
    Raises:
        HTTPException: 404 if document not found or doesn't belong to tenant
        HTTPException: 500 if reprocessing fails
    """
    document_service = DocumentService()
    document = await document_service.get_document(db, document_id, tenant.id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found"
        )
    
    try:
        # Reprocess document in background
        background_tasks.add_task(
            process_document_background,
            document_id=document.id,
            tenant_id=tenant.id,
            reprocess=True,
        )
        
        logger.info(f"Reprocessing document: {document.id} for tenant: {tenant.id}")
        return DocumentResponse.model_validate(document)
    
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error reprocessing document: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while reprocessing the document"
        ) from e

