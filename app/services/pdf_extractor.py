"""
PDF text extraction service
Extracts text from PDF files using pypdf
Reference: https://pypdf.readthedocs.io/
"""
import logging
import time
import io
from typing import List, Tuple
import boto3
from botocore.exceptions import ClientError
from pypdf import PdfReader

from app.core.config import settings

logger = logging.getLogger(__name__)


class PDFExtractor:
    """
    Service for extracting text from PDF files stored in S3
    
    Handles:
    - Downloading PDF from S3
    - Extracting text from each page
    - Returning page-by-page text with page numbers
    """
    
    def __init__(self):
        """Initialize PDF extractor with S3 client"""
        self.s3_client = boto3.client(
            's3',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self.bucket_name = settings.S3_BUCKET_NAME
    
    def extract_text(self, s3_key: str) -> List[Tuple[int, str]]:
        """
        Extract text from PDF stored in S3
        
        Args:
            s3_key: S3 key/path to the PDF file
            
        Returns:
            List of tuples: [(page_number, text), ...]
            Page numbers are 1-based (first page is 1)
            
        Raises:
            Exception: If PDF cannot be downloaded or read
        """
        try:
            extract_start = time.time()
            
            # Download PDF from S3 to memory
            s3_start = time.time()
            logger.info(f"Downloading PDF from S3: {s3_key}")
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            pdf_bytes = response['Body'].read()
            s3_time = time.time() - s3_start
            print(f"[PERF] PDF: S3 download: {s3_time:.3f}s ({len(pdf_bytes) / 1024:.2f} KB)")
            
            # Extract text using pypdf
            extract_text_start = time.time()
            logger.info(f"Extracting text from PDF: {s3_key}")
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)
            
            pages = []
            for page_num, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text()
                    # Clean up text (remove excessive whitespace)
                    text = self._clean_text(text)
                    if text.strip():  # Only add non-empty pages
                        pages.append((page_num, text))
                except Exception as page_error:
                    logger.warning(f"Failed to extract text from page {page_num}: {page_error}")
                    # Continue with other pages even if one fails
                    continue
            
            extract_text_time = time.time() - extract_text_start
            total_time = time.time() - extract_start
            print(f"[PERF] PDF: Text extraction: {extract_text_time:.3f}s ({len(pages)} pages)")
            print(f"[PERF] PDF: Total extraction: {total_time:.3f}s (s3: {s3_time:.3f}s, extract: {extract_text_time:.3f}s)")
            logger.info(f"[PERF] Extracted text from {len(pages)} pages in PDF: {s3_key} - Total: {total_time:.3f}s")
            return pages
            
        except ClientError as e:
            logger.error(f"Failed to download PDF from S3: {e}", exc_info=True)
            raise Exception(f"Failed to download PDF from S3: {e}") from e
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}", exc_info=True)
            raise Exception(f"Failed to extract text from PDF: {e}") from e
    
    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text by removing excessive whitespace
        
        Args:
            text: Raw extracted text
            
        Returns:
            Cleaned text with normalized whitespace
        """
        # Replace multiple spaces with single space
        import re
        text = re.sub(r' +', ' ', text)
        # Replace multiple newlines with double newline (paragraph break)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text

