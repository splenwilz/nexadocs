"""
RAG (Retrieval-Augmented Generation) service
Retrieves relevant document chunks and generates LLM responses with citations
Reference: https://platform.openai.com/docs/guides/embeddings
"""
import asyncio
import logging
import uuid
from typing import List, Dict, Optional
from openai import AsyncOpenAI  # Use async client for better performance
import httpx

from app.core.config import settings
from app.services.embeddings import EmbeddingsService
from app.services.vector_db import VectorDBService

logger = logging.getLogger(__name__)


class RAGService:
    """
    Service for RAG (Retrieval-Augmented Generation) queries
    
    Handles:
    1. Generating query embedding
    2. Searching for similar document chunks
    3. Generating LLM response with retrieved context
    4. Formatting citations
    """
    
    def __init__(self):
        """Initialize RAG service with required services"""
        self.embeddings_service = EmbeddingsService()
        self.vector_db = VectorDBService()
        
        # Configure httpx client with timeout for LLM requests
        # Reference: https://www.python-httpx.org/api/#timeouts
        timeout = httpx.Timeout(
            connect=30.0,
            read=settings.OPENAI_TIMEOUT,
            write=30.0,
            pool=30.0,
        )
        http_client = httpx.AsyncClient(timeout=timeout)
        
        # Use AsyncOpenAI with custom httpx client for timeout configuration
        # Reference: https://github.com/openai/openai-python#async-usage
        self.llm_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            http_client=http_client,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )
        self.llm_model = "gpt-4o-mini"  # Cost-effective model for RAG
        self.max_tokens = 600  # Reduced from 1000 for faster responses (optimization)
        self.max_context_length = 3000  # Limit context to ~3000 chars to reduce input tokens
    
    async def query(
        self,
        tenant_id: uuid.UUID | str,
        question: str,
        max_chunks: int = 5,
        score_threshold: float = 0.7,
    ) -> Dict:
        """
        Answer a question using RAG (Retrieval-Augmented Generation)
        
        Process:
        1. Generate embedding for the question
        2. Search for similar chunks in tenant's vector DB
        3. Generate LLM response using retrieved context
        4. Format citations
        
        Args:
            tenant_id: UUID of the tenant (for tenant isolation)
            question: User's question
            max_chunks: Maximum number of chunks to retrieve
            score_threshold: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            Dictionary with:
                - answer: Generated answer text
                - citations: List of citations with document name and page number
                - chunks_used: Number of chunks used for answer
                
        Raises:
            Exception: If query fails
        """
        # Convert tenant_id to UUID if needed
        if isinstance(tenant_id, str):
            tenant_uuid = uuid.UUID(tenant_id)
        else:
            tenant_uuid = tenant_id
        
        try:
            import time
            total_start = time.time()
            logger.info(f"[RAG] Starting query for tenant {tenant_uuid}, question: {question[:50]}...")
            
            # Step 1: Generate query embedding
            # Now using async client directly (no thread pool overhead)
            embed_start = time.time()
            logger.info(f"[RAG] Step 1: Generating embedding for query...")
            try:
                query_embedding = await self.embeddings_service.generate_embedding(question)
                embed_time = time.time() - embed_start
                print(f"[PERF] RAG: Query embedding: {embed_time:.3f}s")
                logger.info(f"[PERF] RAG: Query embedding: {embed_time:.3f}s")
                logger.info(f"[RAG] Step 1: Successfully generated embedding (length: {len(query_embedding)})")
            except Exception as e:
                logger.error(f"[RAG] Step 1: Failed to generate embedding: {e}", exc_info=True)
                raise
            
            # Step 2: Search for similar chunks
            search_start = time.time()
            logger.info(f"[RAG] Step 2: Searching for similar chunks in tenant {tenant_uuid}...")
            # Lower threshold to 0.2 for better recall (cosine similarity scores can be lower)
            # For cosine similarity, scores range from -1 to 1, but typically 0-1 for normalized vectors
            # A score of 0.2-0.3 can still be relevant, especially for diverse document content
            search_threshold = min(score_threshold, 0.2)  # Use lower of user threshold or 0.2
            print(f"[RAG] DEBUG: Using score threshold: {search_threshold} (original: {score_threshold})")
            try:
                similar_chunks = await self.vector_db.search_similar_chunks(
                    tenant_id=tenant_uuid,
                    query_embedding=query_embedding,
                    limit=max_chunks,
                    score_threshold=search_threshold,
                )
                search_time = time.time() - search_start
                print(f"[PERF] RAG: Vector search: {search_time:.3f}s ({len(similar_chunks)} chunks)")
                logger.info(f"[PERF] RAG: Vector search: {search_time:.3f}s")
                logger.info(f"[RAG] Step 2: Found {len(similar_chunks)} similar chunks")
            except Exception as e:
                logger.error(f"[RAG] Step 2: Failed to search chunks: {e}", exc_info=True)
                raise
            
            if not similar_chunks:
                logger.warning(f"[RAG] No similar chunks found, returning empty response")
                total_time = time.time() - total_start
                print(f"[PERF] RAG: Total (no results): {total_time:.3f}s")
                return {
                    "answer": "I couldn't find any relevant information in your documents to answer this question. Please try rephrasing your question or upload more relevant documents.",
                    "citations": [],
                    "chunks_used": 0,
                }
            
            # Step 3: Build context from retrieved chunks
            context_start = time.time()
            logger.info(f"[RAG] Step 3: Building context from {len(similar_chunks)} chunks...")
            context_parts = []
            citations = []
            seen_docs = set()
            
            for i, chunk in enumerate(similar_chunks):
                logger.debug(f"[RAG] Processing chunk {i+1}/{len(similar_chunks)}: doc={chunk.get('filename', 'unknown')}, page={chunk.get('page_number', 0)}")
                context_parts.append(
                    f"[Document: {chunk['filename']}, Page {chunk['page_number']}]\n{chunk['text']}"
                )
                
                # Build citations (unique by document + page)
                citation_key = (chunk['document_id'], chunk['page_number'])
                if citation_key not in seen_docs:
                    citations.append({
                        "document_id": str(chunk['document_id']),
                        "document_name": chunk['filename'],
                        "page_number": chunk['page_number'],
                    })
                    seen_docs.add(citation_key)
            
            context = "\n\n".join(context_parts)
            
            # Optimize: Truncate context if too long to reduce input tokens and speed up LLM
            # This helps reduce both cost and latency
            if len(context) > self.max_context_length:
                logger.info(f"[RAG] Context too long ({len(context)} chars), truncating to {self.max_context_length} chars")
                context = context[:self.max_context_length] + "\n\n[Context truncated for performance...]"
            
            context_time = time.time() - context_start
            print(f"[PERF] RAG: Context building: {context_time:.3f}s ({len(context)} chars)")
            logger.info(f"[PERF] RAG: Context building: {context_time:.3f}s")
            logger.info(f"[RAG] Step 3: Built context ({len(context)} chars) with {len(citations)} citations")
            
            # Step 4: Generate LLM response
            llm_start = time.time()
            logger.info(f"[RAG] Step 4: Generating LLM response...")
            try:
                answer = await self._generate_answer(question, context)
                llm_time = time.time() - llm_start
                print(f"[PERF] RAG: LLM generation: {llm_time:.3f}s ({len(answer)} chars)")
                logger.info(f"[PERF] RAG: LLM generation: {llm_time:.3f}s")
                logger.info(f"[RAG] Step 4: Successfully generated answer ({len(answer)} chars)")
            except Exception as e:
                logger.error(f"[RAG] Step 4: Failed to generate answer: {e}", exc_info=True)
                raise
            
            total_time = time.time() - total_start
            print(f"[PERF] RAG: Total query time: {total_time:.3f}s (embed: {embed_time:.3f}s, search: {search_time:.3f}s, context: {context_time:.3f}s, llm: {llm_time:.3f}s)")
            logger.info(f"[PERF] RAG: Total query time: {total_time:.3f}s")
            logger.info(f"[RAG] Query completed successfully: {len(similar_chunks)} chunks used, {len(citations)} citations")
            return {
                "answer": answer,
                "citations": citations,
                "chunks_used": len(similar_chunks),
            }
            
        except Exception as e:
            logger.error(f"[RAG] Failed to process RAG query: {e}", exc_info=True)
            import traceback
            logger.error(f"[RAG] Full traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to process RAG query: {e}") from e
    
    async def _generate_answer(self, question: str, context: str) -> str:
        """
        Generate answer using LLM with retrieved context
        
        Uses OpenAI chat completion with system prompt that enforces
        strict adherence to provided context only.
        
        Args:
            question: User's question
            context: Retrieved document chunks as context
            
        Returns:
            Generated answer text
        """
        # Optimized prompt: More concise to reduce input tokens and speed up generation
        # Reference: https://platform.openai.com/docs/guides/prompt-engineering
        system_prompt = """Answer questions using ONLY the provided document context. 
If context is insufficient, say so. Be concise. Cite document names and page numbers."""

        user_prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        
        try:
            logger.info(f"[RAG] _generate_answer: Preparing LLM request...")
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            # Calculate approximate token count for logging (rough estimate: ~4 chars per token)
            total_chars = len(system_prompt) + len(user_prompt)
            est_tokens = total_chars // 4
            logger.info(f"[RAG] _generate_answer: Calling OpenAI API with model {self.llm_model} (~{est_tokens} input tokens, max {self.max_tokens} output tokens)...")
            
            # Use async client directly (no thread pool overhead)
            # Reference: https://github.com/openai/openai-python#async-usage
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                temperature=0.1,  # Low temperature for factual responses
                max_tokens=self.max_tokens,  # Reduced for faster generation
            )
            logger.info(f"[RAG] _generate_answer: OpenAI API call successful")
            
            answer = response.choices[0].message.content
            logger.info(f"[RAG] _generate_answer: Extracted answer ({len(answer) if answer else 0} chars)")
            return answer.strip() if answer else "I couldn't generate an answer. Please try again."
            
        except Exception as e:
            logger.error(f"[RAG] _generate_answer: Failed to generate LLM answer: {e}", exc_info=True)
            import traceback
            logger.error(f"[RAG] _generate_answer: Full traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to generate LLM answer: {e}") from e

