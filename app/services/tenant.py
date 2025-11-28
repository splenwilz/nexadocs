"""
Tenant service for business logic
Handles tenant CRUD operations and validation
Reference: https://docs.sqlalchemy.org/en/20/orm/session_basics.html
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.tenant import Tenant
from app.api.v1.schemas.tenant import TenantCreate, TenantUpdate
from app.services.vector_db import VectorDBService

logger = logging.getLogger(__name__)


class TenantService:
    """
    Service for tenant management operations
    
    Handles all business logic for tenant CRUD operations.
    This service is used by admin endpoints to manage tenants.
    
    Reference: https://fastapi.tiangolo.com/tutorial/bigger-applications/
    """
    
    def __init__(self):
        """Initialize tenant service"""
        self.vector_db = VectorDBService()
    
    async def get_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Optional[Tenant]:
        """
        Get a tenant by ID
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant to fetch
            
        Returns:
            Tenant if found, None otherwise
        """
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()
    
    async def get_tenant_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Optional[Tenant]:
        """
        Get a tenant by slug
        
        Args:
            db: Database session
            slug: Slug identifier of the tenant
            
        Returns:
            Tenant if found, None otherwise
        """
        result = await db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()
    
    async def get_tenant_by_workos_organization_id(
        self,
        db: AsyncSession,
        workos_organization_id: str,
    ) -> Optional[Tenant]:
        """
        Get a tenant by WorkOS organization ID
        
        Args:
            db: Database session
            workos_organization_id: WorkOS organization ID (format: "org_01E4ZCR3C56J083X43JQXF3JK5")
            
        Returns:
            Tenant if found, None otherwise
        """
        result = await db.execute(
            select(Tenant).where(Tenant.workos_organization_id == workos_organization_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create_tenant_by_workos_organization_id(
        self,
        db: AsyncSession,
        workos_organization_id: str,
        organization_name: Optional[str] = None,
    ) -> Tenant:
        """
        Get or create a tenant by WorkOS organization ID.
        
        If tenant exists, returns it. Otherwise, creates a new tenant with:
        - workos_organization_id set to the provided value
        - name from organization_name (or default)
        - slug auto-generated from organization_name or workos_organization_id
        
        Args:
            db: Database session
            workos_organization_id: WorkOS organization ID (format: "org_01E4ZCR3C56J083X43JQXF3JK5")
            organization_name: Optional organization name from WorkOS (for new tenants)
            
        Returns:
            Tenant: Existing or newly created tenant
            
        Raises:
            IntegrityError: If slug conflict occurs (shouldn't happen with auto-generated slugs)
        """
        # Try to get existing tenant
        tenant = await self.get_tenant_by_workos_organization_id(db, workos_organization_id)
        if tenant:
            return tenant
        
        # Create new tenant
        # Generate slug from organization_name or use workos_organization_id
        if organization_name:
            # Generate slug from name: "Acme Corp" -> "acme-corp"
            slug = organization_name.lower().replace(" ", "-").replace("_", "-")
            # Remove special characters, keep only alphanumeric and hyphens
            import re
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            # Ensure slug is not empty and not too long
            if not slug or len(slug) > 100:
                slug = workos_organization_id.replace("org_", "org-")[:100]
        else:
            # Fallback: use workos_organization_id as slug (sanitized)
            slug = workos_organization_id.replace("org_", "org-")[:100]
        
        # Ensure slug is unique by appending suffix if needed
        base_slug = slug
        counter = 1
        while True:
            existing = await self.get_tenant_by_slug(db, slug)
            if not existing:
                break
            slug = f"{base_slug}-{counter}"[:100]
            counter += 1
        
        tenant = Tenant(
            name=organization_name or f"Organization {workos_organization_id}",
            slug=slug,
            workos_organization_id=workos_organization_id,
            is_active=True,
        )
        
        db.add(tenant)
        await db.flush()
        
        logger.info(f"Created tenant: {tenant.id} ({tenant.name}) for WorkOS organization {workos_organization_id}")
        return tenant
    
    async def get_tenants(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> List[Tenant]:
        """
        Get a list of tenants with pagination
        
        Args:
            db: Database session
            skip: Number of tenants to skip (for pagination)
            limit: Maximum number of tenants to return
            include_inactive: Whether to include inactive tenants
            
        Returns:
            List of Tenant objects
        """
        query = select(Tenant)
        
        # Filter out inactive tenants unless explicitly requested
        if not include_inactive:
            query = query.where(Tenant.is_active == True)
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        # Order by creation date (newest first)
        query = query.order_by(Tenant.created_at.desc())
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def create_tenant(
        self,
        db: AsyncSession,
        tenant_data: TenantCreate,
    ) -> Tenant:
        """
        Create a new tenant
        
        Args:
            db: Database session
            tenant_data: Tenant creation data
            
        Returns:
            Created Tenant object
            
        Raises:
            IntegrityError: If slug already exists (will be caught by route handler)
        """
        # Create tenant object
        tenant = Tenant(
            name=tenant_data.name,
            slug=tenant_data.slug,
            is_active=tenant_data.is_active,
        )
        
        db.add(tenant)
        await db.flush()  # Flush to get ID without committing
        
        logger.info(f"Created tenant: {tenant.id} ({tenant.name})")
        return tenant
    
    async def update_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        tenant_data: TenantUpdate,
    ) -> Optional[Tenant]:
        """
        Update an existing tenant
        
        Only updates fields that are explicitly provided (partial update).
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant to update
            tenant_data: Tenant update data (only provided fields will be updated)
            
        Returns:
            Updated Tenant if found, None otherwise
            
        Raises:
            IntegrityError: If slug already exists (will be caught by route handler)
        """
        # Get existing tenant
        tenant = await self.get_tenant(db, tenant_id)
        if not tenant:
            return None
        
        # Get only fields that were explicitly set (exclude_unset=True)
        # This prevents sending None values for omitted fields
        # Reference: https://docs.pydantic.dev/latest/api/standard_library/#pydantic.BaseModel.model_dump
        update_data = tenant_data.model_dump(exclude_unset=True)
        
        # Early return if no fields to update
        if not update_data:
            return tenant
        
        # Update tenant fields
        for field, value in update_data.items():
            setattr(tenant, field, value)
        
        # Manually set updated_at since onupdate doesn't work reliably in async/serverless
        # Reference: Similar pattern in app/services/user.py
        tenant.updated_at = datetime.now(timezone.utc)
        
        await db.flush()  # Flush changes without committing
        
        logger.info(f"Updated tenant: {tenant.id} ({tenant.name})")
        return tenant
    
    async def delete_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> bool:
        """
        Delete a tenant (hard delete)
        
        WARNING: This will cascade delete all related data:
        - Users (via foreign key CASCADE)
        - Documents (via foreign key CASCADE)
        - Conversations (via foreign key CASCADE)
        - Messages (via foreign key CASCADE)
        - ValidatedAnswers (via foreign key CASCADE)
        - Qdrant vector collection (all embeddings)
        
        For production, consider using soft delete (set is_active=False)
        instead of hard delete.
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant to delete
            
        Returns:
            True if tenant was deleted, False if not found
        """
        tenant = await self.get_tenant(db, tenant_id)
        if not tenant:
            return False
        
        # Delete Qdrant collection (all embeddings for this tenant)
        try:
            await self.vector_db.delete_tenant_collection(tenant_id)
            logger.info(f"Deleted Qdrant collection for tenant: {tenant_id}")
        except Exception as e:
            logger.error(f"Failed to delete Qdrant collection for tenant {tenant_id}: {e}", exc_info=True)
            # Continue with database deletion even if Qdrant deletion fails
        
        # Delete tenant (cascade will handle related records)
        await db.delete(tenant)
        await db.flush()
        
        logger.warning(f"Deleted tenant: {tenant_id} ({tenant.name})")
        return True
    
    async def deactivate_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Optional[Tenant]:
        """
        Deactivate a tenant (soft delete)
        
        Sets is_active=False, preventing tenant users from accessing the system.
        Data is preserved for potential reactivation.
        
        This is safer than hard delete and recommended for production.
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant to deactivate
            
        Returns:
            Updated Tenant if found, None otherwise
        """
        tenant = await self.get_tenant(db, tenant_id)
        if not tenant:
            return None
        
        tenant.is_active = False
        # Manually set updated_at since onupdate doesn't work reliably in async/serverless
        tenant.updated_at = datetime.now(timezone.utc)
        await db.flush()
        
        logger.info(f"Deactivated tenant: {tenant.id} ({tenant.name})")
        return tenant
    
    async def activate_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Optional[Tenant]:
        """
        Activate a tenant (reactivate after deactivation)
        
        Sets is_active=True, allowing tenant users to access the system again.
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant to activate
            
        Returns:
            Updated Tenant if found, None otherwise
        """
        tenant = await self.get_tenant(db, tenant_id)
        if not tenant:
            return None
        
        tenant.is_active = True
        # Manually set updated_at since onupdate doesn't work reliably in async/serverless
        tenant.updated_at = datetime.now(timezone.utc)
        await db.flush()
        
        logger.info(f"Activated tenant: {tenant.id} ({tenant.name})")
        return tenant

