"""
Text chunking service
Splits text into smaller chunks for embedding generation
Reference: https://platform.openai.com/docs/guides/embeddings
"""
import logging
from typing import List, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class TextChunker:
    """
    Service for chunking text into smaller pieces for embeddings
    
    Implements sliding window chunking with overlap to preserve context
    across chunk boundaries.
    """
    
    def __init__(self):
        """Initialize chunker with configuration"""
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
    
    def chunk_text(self, text: str, page_number: int) -> List[Tuple[int, str]]:
        """
        Split text into chunks with overlap
        
        Args:
            text: Text to chunk
            page_number: Page number (for tracking)
            
        Returns:
            List of tuples: [(chunk_index, chunk_text), ...]
            Chunk indices are 0-based
        """
        if not text or not text.strip():
            return []
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size
            
            # Extract chunk
            chunk_text = text[start:end].strip()
            
            # Only add non-empty chunks
            if chunk_text:
                chunks.append((chunk_index, chunk_text))
                chunk_index += 1
            
            # Move start position with overlap
            # Overlap ensures context is preserved across chunks
            start = end - self.chunk_overlap
            
            # Prevent infinite loop if overlap is too large
            if start >= end:
                start = end
        
        logger.debug(f"Created {len(chunks)} chunks from text (page {page_number})")
        return chunks
    
    def chunk_pages(self, pages: List[Tuple[int, str]]) -> List[Tuple[int, int, str]]:
        """
        Chunk multiple pages of text
        
        Args:
            pages: List of (page_number, text) tuples
            
        Returns:
            List of tuples: [(chunk_index, page_number, chunk_text), ...]
        """
        all_chunks = []
        chunk_index = 0
        
        for page_number, text in pages:
            # Chunk this page
            page_chunks = self.chunk_text(text, page_number)
            
            # Add chunks with global index
            for _, chunk_text in page_chunks:
                all_chunks.append((chunk_index, page_number, chunk_text))
                chunk_index += 1
        
        logger.info(f"Created {len(all_chunks)} total chunks from {len(pages)} pages")
        return all_chunks

