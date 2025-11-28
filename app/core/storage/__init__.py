"""
Storage backends for file storage
Uses Amazon S3 for document storage
"""
import uuid
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """
    Abstract base class for storage backends.
    
    Currently implements S3 storage for all document uploads.
    The abstraction allows for future extensibility if needed.
    
    Reference: https://docs.python.org/3/library/abc.html
    """

    @abstractmethod
    async def save_file(
        self,
        file: UploadFile,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> str:
        """
        Save a file to storage.
        
        Args:
            file: FastAPI UploadFile object
            tenant_id: UUID of the tenant
            document_id: UUID of the document
        
        Returns:
            str: S3 key (storage path)
        
        Raises:
            Exception: If file save fails
        """
        pass

    @abstractmethod
    async def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from storage.
        
        Args:
            storage_path: Storage path/key returned from save_file
        
        Returns:
            bool: True if file was deleted, False if not found
        
        Raises:
            Exception: If file deletion fails
        """
        pass

    @abstractmethod
    async def file_exists(self, storage_path: str) -> bool:
        """
        Check if a file exists in storage.
        
        Args:
            storage_path: Storage path/key
        
        Returns:
            bool: True if file exists, False otherwise
        """
        pass

    @abstractmethod
    def get_file_url(self, storage_path: str, expires_in: Optional[int] = None) -> str:
        """
        Get a URL to access the file in S3.
        
        Returns a presigned URL if expires_in is provided, otherwise public URL.
        
        Args:
            storage_path: S3 key
            expires_in: Optional expiration time in seconds (for presigned URLs)
        
        Returns:
            str: URL to access the file
        """
        pass

    def _generate_storage_key(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, filename: str
    ) -> str:
        """
        Generate a storage key/path for a document.
        
        Format: tenants/{tenant_id}/documents/{document_id}.pdf
        This ensures tenant isolation at storage level.
        
        Args:
            tenant_id: UUID of the tenant
            document_id: UUID of the document
            filename: Original filename (used to determine extension)
        
        Returns:
            str: Storage key/path
        """
        # Extract file extension from original filename
        ext = Path(filename).suffix or ".pdf"
        
        # Build tenant-specific path
        # Format: tenants/{tenant_id}/documents/{document_id}.pdf
        return f"tenants/{tenant_id}/documents/{document_id}{ext}"


# Import S3Storage after StorageBackend is defined to avoid circular import
# This import happens after StorageBackend class is fully defined
from app.core.storage.s3 import S3Storage


def get_storage_backend() -> StorageBackend:
    """
    Factory function to get the S3 storage backend.
    
    Returns:
        StorageBackend: S3 storage backend instance
    
    Raises:
        ValueError: If S3 configuration is missing
    """
    # Validate S3 configuration
    if not settings.S3_BUCKET_NAME:
        raise ValueError(
            "S3_BUCKET_NAME is required. "
            "Please set S3_BUCKET_NAME in your .env file."
        )
    
    return S3Storage()


__all__ = ["StorageBackend", "S3Storage", "get_storage_backend"]

