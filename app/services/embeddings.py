"""
OpenAI embeddings service
Generates vector embeddings for text chunks
Reference: https://platform.openai.com/docs/guides/embeddings
"""
import asyncio
import logging
import time
from typing import List
from openai import AsyncOpenAI  # Use async client for better performance
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingsService:
    """
    Service for generating embeddings using OpenAI API
    
    Handles:
    - Creating embeddings for text chunks
    - Batch processing for efficiency
    - Error handling and retries
    """
    
    def __init__(self):
        """Initialize embeddings service with OpenAI client"""
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required for document processing. "
                "Please set OPENAI_API_KEY in your .env file."
            )
        # Configure httpx client with increased timeout for large batches
        # Reference: https://www.python-httpx.org/api/#timeouts
        timeout = httpx.Timeout(
            connect=30.0,  # Time to establish connection
            read=settings.OPENAI_TIMEOUT,  # Time to read response (configurable for large batches)
            write=30.0,  # Time to write request
            pool=30.0,  # Time to get connection from pool
        )
        http_client = httpx.AsyncClient(timeout=timeout)
        
        # Use AsyncOpenAI with custom httpx client for timeout configuration
        # Reference: https://github.com/openai/openai-python#async-usage
        # Reference: https://github.com/openai/openai-python/blob/main/src/openai/_client.py#L100
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            http_client=http_client,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )
        self.model = settings.OPENAI_EMBEDDING_MODEL
        self.dimensions = settings.OPENAI_EMBEDDING_DIMENSIONS
        self.max_retries = settings.OPENAI_MAX_RETRIES
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text chunk (async)
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            List of floats representing the embedding vector
            
        Raises:
            Exception: If embedding generation fails
        """
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            raise Exception(f"Failed to generate embedding: {e}") from e
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple text chunks in batch (async)
        
        OpenAI API supports batch processing which is more efficient
        than individual calls.
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            List of embedding vectors (same order as input texts)
            
        Raises:
            Exception: If embedding generation fails
        """
        if not texts:
            return []
        
        try:
            total_start = time.time()
            # OpenAI API supports batch processing
            # Use smaller batch size for very large documents to prevent timeouts
            # Max batch size is typically 2048, but we'll use smaller batches for reliability
            batch_size = 50 if len(texts) > 200 else 100  # Smaller batches for large documents
            all_embeddings = []
            num_batches = (len(texts) + batch_size - 1) // batch_size
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_num = i // batch_size + 1
                logger.debug(f"Generating embeddings for batch {batch_num}/{num_batches} ({len(batch)} texts)")
                
                # Retry logic with exponential backoff
                last_exception = None
                for attempt in range(self.max_retries + 1):
                    try:
                        batch_start = time.time()
                        response = await self.client.embeddings.create(
                            model=self.model,
                            input=batch,
                            dimensions=self.dimensions,
                        )
                        batch_time = time.time() - batch_start
                        print(f"[PERF] Embeddings: Batch {batch_num}/{num_batches}: {batch_time:.3f}s ({len(batch)} texts)")
                        
                        # Extract embeddings in order
                        batch_embeddings = [item.embedding for item in response.data]
                        all_embeddings.extend(batch_embeddings)
                        break  # Success, exit retry loop
                        
                    except Exception as e:
                        last_exception = e
                        if attempt < self.max_retries:
                            # Exponential backoff: wait 2^attempt seconds
                            wait_time = 2 ** attempt
                            logger.warning(
                                f"Embedding generation failed for batch {batch_num}/{num_batches} "
                                f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                                f"Retrying in {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            # Final attempt failed
                            logger.error(
                                f"Failed to generate embeddings for batch {batch_num}/{num_batches} "
                                f"after {self.max_retries + 1} attempts: {e}",
                                exc_info=True
                            )
                            raise Exception(f"Failed to generate embeddings batch after {self.max_retries + 1} attempts: {e}") from e
            
            total_time = time.time() - total_start
            avg_time_per_text = total_time / len(texts) if texts else 0
            print(f"[PERF] Embeddings: Total batch generation: {total_time:.3f}s ({len(all_embeddings)} embeddings, {avg_time_per_text*1000:.2f}ms per text)")
            logger.info(f"[PERF] Generated {len(all_embeddings)} embeddings - Total: {total_time:.3f}s")
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings batch: {e}", exc_info=True)
            raise Exception(f"Failed to generate embeddings batch: {e}") from e
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate number of tokens in text (rough approximation)
        
        Uses simple heuristic: ~4 characters per token
        For more accurate counting, use tiktoken library
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated number of tokens
        """
        # Rough estimate: ~4 characters per token
        # For production, consider using tiktoken for accurate counting
        return len(text) // 4

