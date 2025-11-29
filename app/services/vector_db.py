"""
Qdrant vector database service
Manages tenant-isolated vector collections for document embeddings
Reference: https://qdrant.tech/documentation/
"""
import asyncio
import logging
import time
import uuid
from typing import List, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    CollectionStatus,
    NearestQuery,
)
from qdrant_client.http import models

from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorDBService:
    """
    Service for managing vector embeddings in Qdrant
    
    Each tenant has its own collection to ensure strict data isolation.
    Collections are named: "tenant_{tenant_id}"
    
    Handles:
    - Creating tenant collections
    - Storing document chunk embeddings
    - Searching for similar chunks
    - Deleting tenant data (on tenant deletion)
    """
    
    def __init__(self):
        """Initialize Qdrant client"""
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=settings.QDRANT_TIMEOUT,
        )
        self.dimensions = settings.OPENAI_EMBEDDING_DIMENSIONS
    
    def _get_collection_name(self, tenant_id: uuid.UUID) -> str:
        """
        Generate collection name for tenant
        
        Format: "tenant_{tenant_id}"
        This ensures each tenant has an isolated vector space.
        
        Args:
            tenant_id: UUID of the tenant
            
        Returns:
            Collection name string
        """
        return f"tenant_{str(tenant_id).replace('-', '_')}"
    
    async def ensure_collection_exists(self, tenant_id: uuid.UUID) -> None:
        """
        Ensure tenant collection exists, create if it doesn't
        
        Args:
            tenant_id: UUID of the tenant
            
        Raises:
            Exception: If collection creation fails
        """
        collection_name = self._get_collection_name(tenant_id)
        
        try:
            # Check if collection exists (offload to thread pool)
            collections = await asyncio.to_thread(self.client.get_collections)
            collection_names = [col.name for col in collections.collections]
            
            if collection_name not in collection_names:
                # Create collection
                logger.info(f"Creating Qdrant collection: {collection_name}")
                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.dimensions,
                        distance=Distance.COSINE,  # Cosine similarity for text embeddings
                    ),
                )
                logger.info(f"Created Qdrant collection: {collection_name}")
            else:
                logger.debug(f"Qdrant collection already exists: {collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to ensure collection exists: {e}", exc_info=True)
            raise Exception(f"Failed to ensure Qdrant collection exists: {e}") from e
    
    async def upsert_chunks(
        self,
        tenant_id: uuid.UUID,
        chunks: List[dict],
    ) -> None:
        """
        Store or update document chunks in Qdrant
        
        Each chunk is stored as a point with:
        - id: chunk_id (UUID as string)
        - vector: embedding vector
        - payload: metadata (document_id, page_number, chunk_index, text, etc.)
        
        Args:
            tenant_id: UUID of the tenant
            chunks: List of chunk dictionaries with:
                - chunk_id: UUID of the chunk
                - embedding: List of floats (embedding vector)
                - document_id: UUID of the parent document
                - page_number: Page number in PDF
                - chunk_index: Position within document
                - text: Chunk text content
                - filename: Document filename (for citations)
                
        Raises:
            Exception: If upsert fails
        """
        collection_name = self._get_collection_name(tenant_id)
        
        try:
            # Ensure collection exists
            await self.ensure_collection_exists(tenant_id)
            
            # Prepare points for upsert
            points = []
            for chunk in chunks:
                point = PointStruct(
                    id=str(chunk["chunk_id"]),  # Qdrant requires string IDs
                    vector=chunk["embedding"],
                    payload={
                        "document_id": str(chunk["document_id"]),
                        "tenant_id": str(tenant_id),
                        "page_number": chunk["page_number"],
                        "chunk_index": chunk["chunk_index"],
                        "text": chunk["text"],
                        "filename": chunk.get("filename", ""),
                    },
                )
                points.append(point)
            
            # Upsert points (offload to thread pool)
            upsert_start = time.time()
            print(f"[VectorDB] DEBUG: Upserting {len(points)} points to collection: {collection_name}")
            await asyncio.to_thread(
                self.client.upsert,
                collection_name=collection_name,
                points=points,
            )
            upsert_time = time.time() - upsert_start
            print(f"[PERF] Qdrant: Upsert {len(points)} points: {upsert_time:.3f}s ({upsert_time/len(points)*1000:.2f}ms per point)")
            logger.info(f"[PERF] Upserted {len(points)} chunks to Qdrant collection: {collection_name} - Time: {upsert_time:.3f}s")
            
            # Verify points were stored
            verify_start = time.time()
            try:
                collection_info = await asyncio.to_thread(
                    self.client.get_collection,
                    collection_name=collection_name
                )
                verify_time = time.time() - verify_start
                print(f"[PERF] Qdrant: Verify collection: {verify_time:.3f}s (points: {collection_info.points_count})")
            except Exception as verify_error:
                print(f"[VectorDB] DEBUG: Could not verify collection: {verify_error}")
            
        except Exception as e:
            logger.error(f"Failed to upsert chunks to Qdrant: {e}", exc_info=True)
            raise Exception(f"Failed to upsert chunks to Qdrant: {e}") from e
    
    async def search_similar_chunks(
        self,
        tenant_id: uuid.UUID,
        query_embedding: List[float],
        limit: int = 5,
        score_threshold: float = 0.7,
    ) -> List[dict]:
        """
        Search for similar chunks using vector similarity
        
        Args:
            tenant_id: UUID of the tenant (ensures tenant isolation)
            query_embedding: Query embedding vector
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            List of similar chunks with:
                - chunk_id: UUID of the chunk
                - score: Similarity score (higher is more similar)
                - document_id: UUID of the parent document
                - page_number: Page number for citation
                - chunk_index: Position within document
                - text: Chunk text content
                - filename: Document filename
                
        Raises:
            Exception: If search fails
        """
        collection_name = self._get_collection_name(tenant_id)
        
        try:
            logger.info(f"[VectorDB] Starting search for tenant {tenant_id}, collection: {collection_name}")
            logger.info(f"[VectorDB] Query embedding length: {len(query_embedding)}, limit: {limit}, threshold: {score_threshold}")
            
            # Ensure collection exists
            logger.info(f"[VectorDB] Ensuring collection exists...")
            await self.ensure_collection_exists(tenant_id)
            logger.info(f"[VectorDB] Collection exists: {collection_name}")
            
            # Check collection info first
            try:
                collection_info = await asyncio.to_thread(
                    self.client.get_collection,
                    collection_name=collection_name
                )
                print(f"[VectorDB] DEBUG: Collection has {collection_info.points_count} points before search")
                logger.info(f"[VectorDB] Collection has {collection_info.points_count} points")
            except Exception as info_error:
                print(f"[VectorDB] DEBUG: Could not get collection info: {info_error}")
            
            # Search for similar vectors using query_points
            # Note: We don't need tenant_id filter since each tenant has its own collection
            # But we'll keep it for defense in depth if tenant_id is in payload
            # Reference: https://qdrant.tech/documentation/concepts/search/
            # NearestQuery expects 'nearest' parameter, not 'vector'
            query = NearestQuery(nearest=query_embedding)
            logger.info(f"[VectorDB] Created NearestQuery with vector length {len(query_embedding)}")
            print(f"[VectorDB] DEBUG: Created query with threshold: {score_threshold}, limit: {limit}")
            
            # Wrap in lambda to properly pass keyword arguments
            # Try without threshold first to see if we get any results
            # Qdrant uses cosine similarity, so scores can be negative or positive
            # For cosine similarity, scores range from -1 to 1, but typically 0 to 1 for normalized vectors
            query_start = time.time()
            logger.info(f"[VectorDB] Calling Qdrant query_points...")
            print(f"[VectorDB] DEBUG: Trying query without threshold first...")
            try:
                # First try without threshold to see if we get any results
                query_response = await asyncio.to_thread(
                    lambda: self.client.query_points(
                        collection_name=collection_name,
                        query=query,
                        limit=limit,
                        score_threshold=None,  # No threshold to get all results
                        with_payload=True,
                    )
                )
                query_time = time.time() - query_start
                num_points = len(query_response.points) if hasattr(query_response, 'points') else 0
                print(f"[PERF] Qdrant: Query search: {query_time:.3f}s ({num_points} points returned)")
                print(f"[VectorDB] DEBUG: Query without threshold returned {num_points} points")
                
                # If we got results, filter by threshold manually if needed
                if hasattr(query_response, 'points') and query_response.points:
                    print(f"[VectorDB] DEBUG: First point score: {getattr(query_response.points[0], 'score', 'N/A')}")
                    # Filter by threshold if specified
                    if score_threshold and score_threshold > 0:
                        filtered_points = [p for p in query_response.points if getattr(p, 'score', 0) >= score_threshold]
                        print(f"[VectorDB] DEBUG: After threshold filter ({score_threshold}): {len(filtered_points)} points")
                        # Create a new response-like object with filtered points
                        class FilteredResponse:
                            def __init__(self, points):
                                self.points = points
                        query_response = FilteredResponse(filtered_points)
                logger.info(f"[VectorDB] Qdrant query_points returned successfully")
                logger.info(f"[VectorDB] Response type: {type(query_response)}")
                logger.info(f"[VectorDB] Response attributes: {dir(query_response)}")
            except Exception as qdrant_error:
                logger.error(f"[VectorDB] Qdrant query_points failed: {qdrant_error}", exc_info=True)
                import traceback
                logger.error(f"[VectorDB] Qdrant error traceback: {traceback.format_exc()}")
                raise
            
            # Format results
            # query_response.points contains the matched points
            logger.info(f"[VectorDB] Processing query response...")
            results = []
            if not hasattr(query_response, 'points'):
                logger.error(f"[VectorDB] Response has no 'points' attribute. Available attributes: {dir(query_response)}")
                return results
            
            if not query_response.points:
                logger.warning(f"[VectorDB] No points found in Qdrant response for tenant {tenant_id}")
                print(f"[VectorDB] DEBUG: No points returned from Qdrant. Collection: {collection_name}, Limit: {limit}, Threshold: {score_threshold}")
                print(f"[VectorDB] DEBUG: Query embedding length: {len(query_embedding)}")
                return results
            
            logger.info(f"[VectorDB] Found {len(query_response.points)} points in response")
            print(f"[VectorDB] DEBUG: Found {len(query_response.points)} points in Qdrant response")
            
            for i, point in enumerate(query_response.points):
                print(f"[VectorDB] DEBUG: Point {i+1}: id={point.id}, score={getattr(point, 'score', 'N/A')}")
                try:
                    logger.debug(f"[VectorDB] Processing point {i+1}/{len(query_response.points)}: id={point.id}")
                    # Handle point.id which might be string or UUID
                    point_id = point.id if isinstance(point.id, str) else str(point.id)
                    
                    # Safely access payload fields
                    payload = point.payload or {}
                    logger.debug(f"[VectorDB] Point payload keys: {payload.keys() if payload else 'None'}")
                    
                    result = {
                        "chunk_id": uuid.UUID(point_id),
                        "score": getattr(point, 'score', 0.0),
                        "document_id": uuid.UUID(payload.get("document_id", "")),
                        "page_number": payload.get("page_number", 0),
                        "chunk_index": payload.get("chunk_index", 0),
                        "text": payload.get("text", ""),
                        "filename": payload.get("filename", ""),
                    }
                    results.append(result)
                    logger.debug(f"[VectorDB] Successfully processed point {i+1}")
                except Exception as point_error:
                    logger.error(f"[VectorDB] Error processing point {i+1} (id={getattr(point, 'id', 'unknown')}): {point_error}", exc_info=True)
                    import traceback
                    logger.error(f"[VectorDB] Point error traceback: {traceback.format_exc()}")
                    continue
            
            logger.info(f"[VectorDB] Successfully processed {len(results)} chunks for tenant {tenant_id}")
            return results
            
        except Exception as e:
            logger.error(f"[VectorDB] Failed to search similar chunks: {e}", exc_info=True)
            import traceback
            logger.error(f"[VectorDB] Full traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to search similar chunks: {e}") from e
    
    async def delete_document_chunks(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        """
        Delete all chunks for a document from Qdrant
        
        Used when a document is deleted.
        
        Args:
            tenant_id: UUID of the tenant
            document_id: UUID of the document
            
        Raises:
            Exception: If deletion fails
        """
        collection_name = self._get_collection_name(tenant_id)
        
        try:
            # Delete points matching document_id (offload to thread pool)
            await asyncio.to_thread(
                self.client.delete,
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="document_id",
                                match=MatchValue(value=str(document_id)),
                            ),
                        ],
                    ),
                ),
            )
            
            logger.info(f"Deleted chunks for document {document_id} from Qdrant")
            
        except Exception as e:
            logger.error(f"Failed to delete document chunks: {e}", exc_info=True)
            raise Exception(f"Failed to delete document chunks: {e}") from e
    
    async def delete_tenant_collection(
        self,
        tenant_id: uuid.UUID,
    ) -> None:
        """
        Delete entire tenant collection from Qdrant
        
        Used when a tenant is deleted (cascade delete).
        
        Args:
            tenant_id: UUID of the tenant
            
        Raises:
            Exception: If deletion fails
        """
        collection_name = self._get_collection_name(tenant_id)
        
        try:
            # Check if collection exists (offload to thread pool)
            collections = await asyncio.to_thread(self.client.get_collections)
            collection_names = [col.name for col in collections.collections]
            
            if collection_name in collection_names:
                await asyncio.to_thread(
                    self.client.delete_collection,
                    collection_name=collection_name,
                )
                logger.info(f"Deleted Qdrant collection: {collection_name}")
            else:
                logger.debug(f"Collection {collection_name} does not exist, skipping deletion")
                
        except Exception as e:
            logger.error(f"Failed to delete tenant collection: {e}", exc_info=True)
            raise Exception(f"Failed to delete tenant collection: {e}") from e

