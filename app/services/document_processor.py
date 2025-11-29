"""
Document processing service
Orchestrates the complete document processing pipeline:
1. Text extraction from PDF
2. Text chunking
3. Embedding generation
4. Database storage
"""
import logging
import time
from datetime import datetime, timezone
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.pdf_extractor import PDFExtractor
from app.services.text_chunker import TextChunker
from app.services.embeddings import EmbeddingsService
from app.services.vector_db import VectorDBService

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Service for processing documents through the RAG pipeline
    
    Orchestrates:
    1. PDF text extraction
    2. Text chunking
    3. Embedding generation
    4. Database storage of chunks
    """
    
    def __init__(self):
        """Initialize processor with required services"""
        self.pdf_extractor = PDFExtractor()
        self.text_chunker = TextChunker()
        self.embeddings_service = EmbeddingsService()
        self.vector_db = VectorDBService()
    
    async def process_document(
        self,
        db: AsyncSession,
        document: Document,
    ) -> Document:
        """
        Process a document through the complete pipeline
        
        Steps:
        1. Update status to PROCESSING
        2. Extract text from PDF (S3)
        3. Chunk text into smaller pieces
        4. Generate embeddings for chunks
        5. Save chunks to database
        6. Update document status to COMPLETED
        
        Args:
            db: Database session
            document: Document to process
            
        Returns:
            Updated Document with processing results
            
        Raises:
            Exception: If any step fails (document status set to FAILED)
        """
        try:
            total_start = time.time()
            
            # Update status to PROCESSING
            document.status = DocumentStatus.PROCESSING
            document.error_message = None
            await db.flush()
            logger.info(f"Started processing document: {document.id}")
            
            # Step 1: Extract text from PDF
            extract_start = time.time()
            logger.info(f"Extracting text from PDF: {document.file_path}")
            pages = self.pdf_extractor.extract_text(document.file_path)
            extract_time = time.time() - extract_start
            print(f"[PERF] PDF extraction: {extract_time:.3f}s ({len(pages) if pages else 0} pages)")
            logger.info(f"[PERF] PDF extraction: {extract_time:.3f}s")
            
            if not pages:
                raise Exception("No text extracted from PDF")
            
            document.page_count = len(pages)
            logger.info(f"Extracted {len(pages)} pages from PDF")
            
            # Step 2: Chunk text
            chunk_start = time.time()
            logger.info(f"Chunking text from {len(pages)} pages")
            chunks = self.text_chunker.chunk_pages(pages)
            chunk_time = time.time() - chunk_start
            print(f"[PERF] Text chunking: {chunk_time:.3f}s ({len(chunks) if chunks else 0} chunks)")
            logger.info(f"[PERF] Text chunking: {chunk_time:.3f}s")
            
            if not chunks:
                raise Exception("No chunks created from text")
            
            logger.info(f"Created {len(chunks)} chunks")
            
            # Step 3: Generate embeddings
            # Extract just the text for embedding generation
            chunk_texts = [chunk_text for _, _, chunk_text in chunks]
            embedding_start = time.time()
            logger.info(f"Generating embeddings for {len(chunk_texts)} chunks")
            embeddings = await self.embeddings_service.generate_embeddings_batch(chunk_texts)
            embedding_time = time.time() - embedding_start
            print(f"[PERF] Embedding generation: {embedding_time:.3f}s ({len(embeddings)} embeddings)")
            logger.info(f"[PERF] Embedding generation: {embedding_time:.3f}s")
            
            if len(embeddings) != len(chunks):
                raise Exception(f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}")
            
            logger.info(f"Generated {len(embeddings)} embeddings")
            
            # Step 4: Save chunks to database first (to get IDs)
            db_save_start = time.time()
            logger.info(f"Saving {len(chunks)} chunks to database")
            chunk_objects = []
            
            for (chunk_index, page_number, chunk_text), embedding in zip(chunks, embeddings):
                # Estimate token count
                token_count = self.embeddings_service.estimate_tokens(chunk_text)
                
                # Create database chunk (without embedding - stored in Qdrant)
                chunk = DocumentChunk(
                    document_id=document.id,
                    tenant_id=document.tenant_id,
                    chunk_index=chunk_index,
                    page_number=page_number,
                    text=chunk_text,
                    embedding=None,  # Embeddings stored in Qdrant, not PostgreSQL
                    token_count=token_count,
                )
                chunk_objects.append(chunk)
                db.add(chunk)
            
            # Flush chunks to database to get IDs
            await db.flush()
            db_save_time = time.time() - db_save_start
            print(f"[PERF] Database save chunks: {db_save_time:.3f}s ({len(chunk_objects)} chunks)")
            logger.info(f"[PERF] Database save chunks: {db_save_time:.3f}s")
            logger.info(f"Saved {len(chunk_objects)} chunks to database")
            
            # Step 5: Prepare chunks for Qdrant (now that we have IDs)
            qdrant_prep_start = time.time()
            qdrant_chunks = []
            for chunk, (_, _, _), embedding in zip(chunk_objects, chunks, embeddings):
                qdrant_chunks.append({
                    "chunk_id": chunk.id,  # Now chunk.id is available after flush
                    "document_id": document.id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "embedding": embedding,
                    "filename": document.filename,
                })
            qdrant_prep_time = time.time() - qdrant_prep_start
            print(f"[PERF] Qdrant prep: {qdrant_prep_time:.3f}s")
            
            # Store embeddings in Qdrant
            qdrant_start = time.time()
            logger.info(f"Storing {len(qdrant_chunks)} embeddings in Qdrant")
            await self.vector_db.upsert_chunks(document.tenant_id, qdrant_chunks)
            qdrant_time = time.time() - qdrant_start
            print(f"[PERF] Qdrant upsert: {qdrant_time:.3f}s ({len(qdrant_chunks)} points)")
            logger.info(f"[PERF] Qdrant upsert: {qdrant_time:.3f}s")
            logger.info(f"Stored {len(qdrant_chunks)} embeddings in Qdrant")
            
            # Step 6: Update document status to COMPLETED
            status_start = time.time()
            document.status = DocumentStatus.COMPLETED
            document.chunk_count = len(chunk_objects)
            document.processed_at = datetime.now(timezone.utc)
            document.error_message = None
            await db.flush()
            status_time = time.time() - status_start
            print(f"[PERF] Status update: {status_time:.3f}s")
            
            total_time = time.time() - total_start
            print(f"[PERF] Total processing time: {total_time:.3f}s (extract: {extract_time:.3f}s, chunk: {chunk_time:.3f}s, embed: {embedding_time:.3f}s, db: {db_save_time:.3f}s, qdrant: {qdrant_time:.3f}s)")
            logger.info(
                f"[PERF] Completed processing document {document.id}: "
                f"{document.page_count} pages, {document.chunk_count} chunks - Total: {total_time:.3f}s"
            )
            
            return document
            
        except Exception as e:
            # Update document status to FAILED
            logger.error(f"Failed to process document {document.id}: {e}", exc_info=True)
            
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)[:2000]  # Truncate to fit in database
            document.processed_at = datetime.now(timezone.utc)
            await db.flush()
            
            # Re-raise to allow caller to handle
            raise
    
    async def reprocess_document(
        self,
        db: AsyncSession,
        document: Document,
    ) -> Document:
        """
        Reprocess a document (delete old chunks and reprocess)
        
        Useful for:
        - Fixing processing errors
        - Updating embeddings after model change
        - Re-chunking with different settings
        
        Args:
            db: Database session
            document: Document to reprocess
            
        Returns:
            Updated Document with new processing results
        """
        # Delete existing chunks from Qdrant
        try:
            await self.vector_db.delete_document_chunks(document.tenant_id, document.id)
            logger.info(f"Deleted chunks from Qdrant for document {document.id}")
        except Exception as e:
            logger.warning(f"Failed to delete chunks from Qdrant: {e}")
            # Continue with database deletion
        
        # Delete existing chunks from database
        result = await db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        existing_chunks = result.scalars().all()
        
        for chunk in existing_chunks:
            await db.delete(chunk)
        
        await db.flush()
        logger.info(f"Deleted {len(existing_chunks)} existing chunks from database for document {document.id}")
        
        # Reset document status
        document.status = DocumentStatus.PENDING
        document.page_count = None
        document.chunk_count = None
        document.processed_at = None
        document.error_message = None
        await db.flush()
        
        # Process document
        return await self.process_document(db, document)

