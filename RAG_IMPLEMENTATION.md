# RAG Pipeline Implementation

## Overview

This document describes the complete RAG (Retrieval-Augmented Generation) pipeline implementation for the multi-tenant AI knowledge assistant.

## Architecture

The RAG pipeline consists of:

1. **Document Processing Pipeline**: Extracts text, chunks documents, generates embeddings
2. **Vector Database (Qdrant)**: Stores embeddings with tenant isolation
3. **RAG Service**: Retrieves relevant chunks and generates LLM responses
4. **Chat API**: Exposes conversation endpoints for users

## Components

### 1. Document Processing Pipeline

**Files:**
- `app/services/pdf_extractor.py` - PDF text extraction from S3
- `app/services/text_chunker.py` - Text chunking with overlap
- `app/services/embeddings.py` - OpenAI embedding generation
- `app/services/document_processor.py` - Orchestrates the complete pipeline

**Process:**
1. Document uploaded → Status: `PENDING`
2. Background task starts → Status: `PROCESSING`
3. Extract text from PDF (page-by-page)
4. Chunk text into smaller pieces (configurable size/overlap)
5. Generate embeddings using OpenAI
6. Store chunks in PostgreSQL (metadata)
7. Store embeddings in Qdrant (vectors)
8. Status: `COMPLETED` or `FAILED`

### 2. Vector Database (Qdrant)

**File:** `app/services/vector_db.py`

**Features:**
- Tenant-isolated collections: `tenant_{tenant_id}`
- Stores embeddings with metadata (document_id, page_number, text, filename)
- Semantic search with cosine similarity
- Automatic collection creation
- Tenant deletion removes entire collection

**Configuration:**
```env
QDRANT_URL=http://localhost:6333  # Default: local Qdrant
QDRANT_API_KEY=                    # Optional: for Qdrant Cloud
QDRANT_TIMEOUT=30                  # Request timeout in seconds
```

### 3. RAG Service

**File:** `app/services/rag.py`

**Process:**
1. Generate embedding for user's question
2. Search Qdrant for similar chunks (tenant-scoped)
3. Retrieve top N chunks with similarity scores
4. Build context from retrieved chunks
5. Generate LLM response using context
6. Format citations (document name + page number)

**LLM Model:** `gpt-4o-mini` (cost-effective for RAG)

### 4. Chat API

**Files:**
- `app/api/v1/routes/chat.py` - Chat endpoints
- `app/api/v1/schemas/chat.py` - Request/response schemas
- `app/services/chat.py` - Conversation management

**Endpoints:**
- `POST /api/v1/chat/message` - Send a message, get AI response
- `GET /api/v1/chat/conversations` - List user's conversations
- `GET /api/v1/chat/conversations/{id}` - Get conversation with messages
- `DELETE /api/v1/chat/conversations/{id}` - Delete conversation

## Database Models

### DocumentChunk

Stores text chunks with metadata:
- `id` - UUID
- `document_id` - Parent document
- `tenant_id` - Tenant isolation
- `chunk_index` - Position in document
- `page_number` - Page number for citations
- `text` - Chunk text content
- `embedding` - NULL (stored in Qdrant)
- `token_count` - Estimated tokens

## Configuration

### Required Environment Variables

```env
# OpenAI (required for processing)
OPENAI_API_KEY=sk-your-key-here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small  # Default
OPENAI_EMBEDDING_DIMENSIONS=1536              # Default

# Qdrant (optional - defaults to localhost)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                                # Optional
QDRANT_TIMEOUT=30

# Document Processing
CHUNK_SIZE=1000                                # Characters per chunk
CHUNK_OVERLAP=200                              # Overlap between chunks
```

## Setup Instructions

### 1. Install Dependencies

```bash
uv sync
```

This installs:
- `openai>=1.0.0` - OpenAI API client
- `pypdf>=4.0.0` - PDF text extraction
- `qdrant-client>=1.7.0` - Qdrant vector DB client

### 2. Set Up Qdrant

**Option A: Local Qdrant (Docker)**
```bash
docker run -p 6333:6333 qdrant/qdrant
```

**Option B: Qdrant Cloud**
- Sign up at https://cloud.qdrant.io
- Get API key and URL
- Set `QDRANT_URL` and `QDRANT_API_KEY` in `.env`

### 3. Configure OpenAI

Add to `.env`:
```env
OPENAI_API_KEY=sk-your-key-here
```

### 4. Run Migration

```bash
uv run alembic upgrade head
```

This creates the `document_chunks` table.

## Usage

### Upload and Process Document

```bash
curl -X POST "http://localhost:8000/api/v1/documents" \
  -H "Authorization: Bearer {token}" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "id": "uuid",
  "status": "pending",
  ...
}
```

Document will be processed in the background. Check status:
```bash
curl "http://localhost:8000/api/v1/documents/{document_id}" \
  -H "Authorization: Bearer {token}"
```

When `status` is `"completed"`, the document is ready for queries.

### Ask a Question

```bash
curl -X POST "http://localhost:8000/api/v1/chat/message" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the main topic of the document?",
    "conversation_id": null
  }'
```

Response:
```json
{
  "answer": "Based on the documents...",
  "citations": [
    {
      "document_id": "uuid",
      "document_name": "document.pdf",
      "page_number": 1
    }
  ],
  "chunks_used": 3,
  "conversation_id": "uuid",
  "message_id": "uuid"
}
```

## Tenant Isolation

**Strict isolation at every level:**

1. **Database**: All queries filter by `tenant_id`
2. **S3 Storage**: Files stored in `tenants/{tenant_id}/documents/`
3. **Qdrant**: Separate collection per tenant (`tenant_{tenant_id}`)
4. **API**: Tenant extracted from JWT, enforced in all endpoints

## Error Handling

- **Document Processing Failures**: Status set to `FAILED`, error message stored
- **Qdrant Connection Issues**: Logged, processing continues if possible
- **OpenAI API Errors**: Document marked as `FAILED`, error details logged
- **Missing Documents**: Graceful error messages to users

## Performance Considerations

- **Batch Embedding Generation**: Processes chunks in batches of 100
- **Async Operations**: All I/O operations are async
- **Background Processing**: Documents processed asynchronously after upload
- **Vector Search**: Qdrant handles similarity search efficiently

## Next Steps

1. **Test the pipeline**: Upload a document and verify processing
2. **Monitor Qdrant**: Check collection creation and search performance
3. **Tune Parameters**: Adjust `CHUNK_SIZE`, `CHUNK_OVERLAP`, `score_threshold`
4. **Add OCR**: For scanned PDFs (using Tesseract or cloud OCR service)

## Troubleshooting

### Document Stuck in PROCESSING

Check logs for errors. Reprocess:
```python
# Via API (if endpoint exists) or directly:
processor = DocumentProcessor()
await processor.reprocess_document(db, document)
```

### Qdrant Connection Errors

- Verify Qdrant is running: `curl http://localhost:6333/health`
- Check `QDRANT_URL` in `.env`
- For Qdrant Cloud, verify `QDRANT_API_KEY`

### OpenAI API Errors

- Verify `OPENAI_API_KEY` is set
- Check API quota/limits
- Verify model name is correct

