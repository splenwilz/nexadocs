"""
Tenant service for business logic
Handles tenant CRUD operations and validation
Reference: https://docs.sqlalchemy.org/en/20/orm/session_basics.html
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.tenant import Tenant
from app.api.v1.schemas.tenant import TenantCreate, TenantUpdate
from app.services.vector_db import VectorDBService
from app.services.workos_org import WorkOSOrganizationService

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
        self.workos_orgs = WorkOSOrganizationService()
    
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
        
        This method is race-safe: if multiple concurrent requests try to create
        a tenant for the same WorkOS organization, only one will succeed. The others
        will catch IntegrityError, rollback, and return the tenant created by the
        first request.
        
        Args:
            db: Database session
            workos_organization_id: WorkOS organization ID (format: "org_01E4ZCR3C56J083X43JQXF3JK5")
            organization_name: Optional organization name from WorkOS (for new tenants)
            
        Returns:
            Tenant: Existing or newly created tenant
            
        Raises:
            IntegrityError: If both workos_organization_id and slug conflict (very rare edge case)
        """
        # Try to get existing tenant
        tenant = await self.get_tenant_by_workos_organization_id(db, workos_organization_id)
        if tenant:
            return tenant
        
        # Create new tenant
        # Generate slug from organization_name or use workos_organization_id
        max_length = 100  # Database column limit
        if organization_name:
            # Generate slug from name: "Acme Corp" -> "acme-corp"
            slug = organization_name.lower().replace(" ", "-").replace("_", "-")
            # Remove special characters, keep only alphanumeric and hyphens
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            # Fallback to WorkOS org ID if slug ends up empty
            if not slug:
                slug = workos_organization_id.replace("org_", "org-")
        else:
            # Fallback: use workos_organization_id as slug (sanitized)
            slug = workos_organization_id.replace("org_", "org-")
        
        # Enforce maximum length before uniqueness checks
        # Truncate to leave room for counter suffix (e.g., "-123")
        # Reserve space for counter to prevent infinite loop when slug is exactly max_length
        slug = slug[:max_length]
        
        # Ensure slug is unique by appending suffix if needed
        base_slug = slug
        counter = 1
        while True:
            existing = await self.get_tenant_by_slug(db, slug)
            if not existing:
                break
            # Append counter - if base_slug is max_length, truncate it to leave room
            # This prevents infinite loop when base_slug is exactly 100 chars
            if len(base_slug) >= max_length:
                # Truncate base_slug to leave room for "-{counter}"
                base_slug = base_slug[:max_length - len(str(counter)) - 1]
            slug = f"{base_slug}-{counter}"
            # Final safety check: ensure slug doesn't exceed max_length
            if len(slug) > max_length:
                slug = slug[:max_length]
            counter += 1
        
        tenant = Tenant(
            name=organization_name or f"Organization {workos_organization_id}",
            slug=slug,
            workos_organization_id=workos_organization_id,
            is_active=True,
        )
        
        db.add(tenant)
        try:
            await db.flush()
        except IntegrityError:
            # Race condition: another request created the tenant concurrently
            # Rollback this transaction and return the existing tenant
            await db.rollback()
            logger.info(
                f"Tenant creation race condition detected for WorkOS org {workos_organization_id}. "
                f"Re-querying for existing tenant."
            )
            # Re-query to get the tenant created by the other request
            existing_tenant = await self.get_tenant_by_workos_organization_id(db, workos_organization_id)
            if existing_tenant:
                logger.info(f"Returning existing tenant {existing_tenant.id} created by concurrent request")
                return existing_tenant
            # If tenant still doesn't exist after rollback, re-raise the IntegrityError
            # This handles the edge case where both workos_organization_id and slug conflict
            raise
        
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
            query = query.where(Tenant.is_active.is_(True))
        
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

    async def provision_tenant(
        self,
        db: AsyncSession,
        name: str,
        domains: Sequence[str] | None = None,
    ) -> Tenant:
        """
        Create a tenant and a backing WorkOS organization.

        Reference: https://workos.com/docs/reference/authkit/authentication-errors/organization-authentication-required-error
        """
        # Generate a unique slug automatically so callers do not need to supply one.
        slug_seed = name.lower().strip()
        unique_slug = await self._generate_unique_slug(db, slug_seed)

        # Provision the WorkOS organization before writing to our DB.
        # If DB insert fails, we'll clean up the orphaned WorkOS org.
        workos_org = await self.workos_orgs.create_organization(name=name, domains=domains)
        workos_org_id = workos_org["id"]

        tenant = Tenant(
            name=name,
            slug=unique_slug,
            workos_organization_id=workos_org_id,
            is_active=True,
        )

        try:
            db.add(tenant)
            await db.flush()
        except Exception as db_error:
            # Database operation failed - clean up orphaned WorkOS organization
            # This prevents orphaned organizations if DB insert fails (constraint violation, connection issue, etc.)
            logger.warning(
                f"Database insert failed after WorkOS organization creation for tenant '{name}'. "
                f"Cleaning up orphaned WorkOS organization {workos_org_id}. Error: {db_error}"
            )
            try:
                await self.workos_orgs.delete_organization(workos_org_id)
                logger.info(f"Successfully cleaned up orphaned WorkOS organization {workos_org_id}")
            except Exception as cleanup_error:
                # Log cleanup failure but don't mask the original error
                logger.error(
                    f"Failed to clean up orphaned WorkOS organization {workos_org_id} after DB failure. "
                    f"Cleanup error: {cleanup_error}. Original error: {db_error}",
                    exc_info=True
                )
            # Re-raise the original database error
            raise

        logger.info(
            "Provisioned tenant %s with WorkOS org %s",
            tenant.id,
            workos_org_id,
        )
        return tenant

    async def _generate_unique_slug(self, db: AsyncSession, base_slug: str) -> str:
        """
        Sanitize and deduplicate slugs for automated provisioning.
        
        Enforces max_length (100) to match database column limit and prevent
        potential database errors. This ensures consistency with other slug
        generation methods.
        """
        max_length = 100  # Database column limit (matches Tenant.slug String(100))
        slug = re.sub(r"[^a-z0-9-]", "-", base_slug) or f"tenant-{uuid.uuid4().hex[:8]}"
        slug = slug.strip("-")
        if not slug:
            slug = f"tenant-{uuid.uuid4().hex[:8]}"
        
        # Enforce maximum length before uniqueness checks
        # Truncate to leave room for counter suffix (e.g., "-123")
        slug = slug[:max_length]

        candidate = slug
        counter = 1
        while True:
            existing = await self.get_tenant_by_slug(db, candidate)
            if not existing:
                return candidate
            # Append counter - if slug is max_length, truncate it to leave room
            # This prevents infinite loop when slug is exactly 100 chars
            if len(slug) >= max_length:
                slug = slug[:max_length - len(str(counter)) - 1]
            candidate = f"{slug}-{counter}"
            # Final safety check: ensure candidate doesn't exceed max_length
            if len(candidate) > max_length:
                candidate = candidate[:max_length]
            counter += 1
    
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

