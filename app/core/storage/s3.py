"""
S3 storage backend using boto3
Stores all files in Amazon S3 with tenant isolation
"""
import uuid
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)


# Import StorageBackend from parent module after it's defined
# This avoids circular import since __init__.py imports S3Storage
import sys
_parent_module = sys.modules.get(__name__.rsplit('.', 1)[0])
if _parent_module and hasattr(_parent_module, 'StorageBackend'):
    StorageBackend = _parent_module.StorageBackend
else:
    # Fallback: this shouldn't happen in normal execution
    raise ImportError("StorageBackend not found in parent module")


class S3Storage(StorageBackend):
    """
    Amazon S3 storage backend.
    
    Stores all files in S3 bucket with path: tenants/{tenant_id}/documents/{document_id}.pdf
    This is the only storage backend - all documents are stored in S3.
    
    Requires:
    - S3_BUCKET_NAME (required)
    - AWS_REGION (default: us-east-1)
    - AWS_ACCESS_KEY_ID (optional if using IAM role or credentials file)
    - AWS_SECRET_ACCESS_KEY (optional if using IAM role or credentials file)
    """

    def __init__(self):
        """Initialize S3 storage with boto3 client"""
        self.bucket_name = settings.S3_BUCKET_NAME
        self.region = settings.AWS_REGION
        
        # Initialize S3 client
        # boto3 will use credentials from:
        # 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        # 2. AWS credentials file (~/.aws/credentials)
        # 3. IAM role (if running on EC2)
        # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
        self.s3_client = boto3.client(
            's3',
            region_name=self.region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        
        logger.info(f"Initialized S3 storage: bucket={self.bucket_name}, region={self.region}")

    async def save_file(
        self,
        file: UploadFile,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> str:
        """
        Upload file to S3.
        
        Args:
            file: FastAPI UploadFile object
            tenant_id: UUID of the tenant
            document_id: UUID of the document
        
        Returns:
            str: S3 key (storage path)
        
        Raises:
            Exception: If S3 upload fails
        """
        # Generate S3 key
        s3_key = self._generate_storage_key(tenant_id, document_id, file.filename or "document.pdf")
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Upload to S3
        # Use put_object for better control over metadata
        # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content,
                ContentType=file.content_type or "application/pdf",
                Metadata={
                    "tenant_id": str(tenant_id),
                    "document_id": str(document_id),
                    "original_filename": file.filename or "document.pdf",
                },
            )
            
            logger.info(f"Uploaded file to S3: s3://{self.bucket_name}/{s3_key} (size: {file_size} bytes)")
            return s3_key
        
        except ClientError as e:
            logger.error(f"Failed to upload file to S3: {e}", exc_info=True)
            raise Exception(f"S3 upload failed: {str(e)}") from e

    async def delete_file(self, storage_path: str) -> bool:
        """
        Delete file from S3.
        
        Args:
            storage_path: S3 key
        
        Returns:
            bool: True if file was deleted, False if not found
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_path,
            )
            logger.info(f"Deleted file from S3: s3://{self.bucket_name}/{storage_path}")
            return True
        
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchKey":
                logger.warning(f"File not found in S3: s3://{self.bucket_name}/{storage_path}")
                return False
            logger.error(f"Failed to delete file from S3: {e}", exc_info=True)
            return False

    async def file_exists(self, storage_path: str) -> bool:
        """
        Check if file exists in S3.
        
        Args:
            storage_path: S3 key
        
        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=storage_path,
            )
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                return False
            # Re-raise other errors
            logger.error(f"Error checking file existence in S3: {e}", exc_info=True)
            raise

    def get_file_url(self, storage_path: str, expires_in: Optional[int] = None) -> str:
        """
        Get URL to access file in S3.
        
        If expires_in is provided, returns a presigned URL (temporary access).
        Otherwise, returns a public URL (if bucket is public) or presigned URL.
        
        Args:
            storage_path: S3 key
            expires_in: Optional expiration time in seconds (default: 1 hour)
        
        Returns:
            str: URL to access the file
        """
        if expires_in is None:
            expires_in = 3600  # Default: 1 hour
        
        try:
            # Generate presigned URL
            # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/generate_presigned_url.html
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': storage_path,
                },
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}", exc_info=True)
            # Fallback to public URL (if bucket is public)
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{storage_path}"

