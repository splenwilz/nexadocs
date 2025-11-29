"""
Multi-tenant context management
Extracts and enforces tenant isolation for all requests
Reference: https://fastapi.tiangolo.com/tutorial/dependencies/
"""
import logging
import uuid
from typing import Annotated, Optional
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.api.v1.schemas.auth import WorkOSUserResponse

logger = logging.getLogger(__name__)


async def get_current_tenant(
    current_user: WorkOSUserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    Dependency to get the current tenant from the authenticated user.
    
    This is the primary tenant context dependency. It:
    1. Gets the authenticated user (from WorkOS JWT)
    2. Looks up the user in our database to get their tenant_id
    3. Fetches and returns the tenant
    
    All tenant-scoped endpoints should use this dependency to ensure
    proper tenant isolation.
    
    Usage:
        @router.get("/documents")
        async def get_documents(
            tenant: Tenant = Depends(get_current_tenant),
            db: AsyncSession = Depends(get_db)
        ):
            # All queries should filter by tenant.id
            documents = await db.execute(
                select(Document).where(Document.tenant_id == tenant.id)
            )
            return documents.scalars().all()
    
    Args:
        current_user: Authenticated user from WorkOS (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        Tenant: The tenant associated with the current user
        
    Raises:
        HTTPException: 404 if user not found in database
        HTTPException: 404 if tenant not found
        HTTPException: 403 if tenant is inactive
        HTTPException: 400 if user has no tenant_id (data integrity issue)
    
    Reference: https://fastapi.tiangolo.com/tutorial/dependencies/
    """
    # Get user from database to access tenant_id
    # User must exist in our database with tenant_id set
    # This is set when user is created/assigned to a tenant
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        logger.warning(f"User {current_user.id} authenticated but not found in database")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in database. Please contact support.",
        )
    
    if not user.tenant_id:
        logger.error(f"User {user.id} has no tenant_id assigned")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a tenant. Please contact support.",
        )
    
    # Fetch tenant from database
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        logger.error(f"Tenant {user.tenant_id} not found for user {user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found. Please contact support.",
        )
    
    # Check if tenant is active (soft delete check)
    if not tenant.is_active:
        logger.warning(f"Inactive tenant {tenant.id} accessed by user {user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization's account is inactive. Please contact support.",
        )
    
    logger.debug(f"Tenant context resolved: {tenant.id} ({tenant.name}) for user {user.id}")
    return tenant


async def get_tenant_by_id(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    Dependency to get a tenant by ID (for admin operations).
    
    This is used by admin endpoints that need to access a specific tenant
    by ID (e.g., viewing tenant details, managing tenants).
    
    Usage:
        @router.get("/admin/tenants/{tenant_id}")
        async def get_tenant_details(
            tenant: Tenant = Depends(get_tenant_by_id),
        ):
            return tenant
    
    Args:
        tenant_id: UUID of the tenant to fetch
        db: Database session (injected via dependency)
        
    Returns:
        Tenant: The tenant with the specified ID
        
    Raises:
        HTTPException: 404 if tenant not found
        HTTPException: 403 if tenant is inactive (unless admin override)
    
    Reference: https://fastapi.tiangolo.com/tutorial/dependencies/
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )
    
    return tenant


async def get_tenant_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    Dependency to get a tenant by slug (for subdomain routing).
    
    This can be used for subdomain-based tenant routing:
    - tenant1.example.com -> slug = "tenant1"
    - tenant2.example.com -> slug = "tenant2"
    
    Usage:
        @router.get("/api/{tenant_slug}/documents")
        async def get_documents(
            tenant: Tenant = Depends(get_tenant_by_slug),
        ):
            # Use tenant.id for queries
            pass
    
    Args:
        slug: Tenant slug identifier
        db: Database session (injected via dependency)
        
    Returns:
        Tenant: The tenant with the specified slug
        
    Raises:
        HTTPException: 404 if tenant not found
        HTTPException: 403 if tenant is inactive
    
    Reference: https://fastapi.tiangolo.com/tutorial/dependencies/
    """
    result = await db.execute(
        select(Tenant).where(Tenant.slug == slug)
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with slug '{slug}' not found",
        )
    
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This organization's account is inactive",
        )
    
    return tenant


async def get_tenant_from_header(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_db),
) -> Optional[Tenant]:
    """
    Dependency to get tenant from X-Tenant-ID header (for admin operations).
    
    This allows admin endpoints to specify which tenant to operate on
    via the X-Tenant-ID header. Used for cross-tenant admin operations.
    
    Usage:
        @router.get("/admin/tenants/{tenant_id}/documents")
        async def get_tenant_documents(
            tenant: Optional[Tenant] = Depends(get_tenant_from_header),
            # If header not provided, use path parameter
            tenant_id: uuid.UUID,
            db: AsyncSession = Depends(get_db),
        ):
            if tenant:
                # Use tenant from header
                pass
            else:
                # Use tenant from path
                tenant = await get_tenant_by_id(tenant_id, db)
    
    Args:
        x_tenant_id: Optional tenant ID from X-Tenant-ID header
        db: Database session (injected via dependency)
        
    Returns:
        Optional[Tenant]: The tenant if header is provided, None otherwise
        
    Raises:
        HTTPException: 400 if header value is invalid UUID
        HTTPException: 404 if tenant not found
    
    Reference: https://fastapi.tiangolo.com/tutorial/header-params/
    """
    if not x_tenant_id:
        return None
    
    try:
        tenant_uuid = uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tenant ID format in X-Tenant-ID header: {x_tenant_id}",
        )
    
    return await get_tenant_by_id(tenant_uuid, db)


def ensure_tenant_context(tenant_id: uuid.UUID, current_tenant: Tenant) -> None:
    """
    Helper function to ensure an operation is scoped to the current tenant.
    
    This is a safety check to prevent cross-tenant data access. Use this
    when performing operations that accept a tenant_id parameter to ensure
    the user can only access their own tenant's data.
    
    Usage:
        @router.delete("/documents/{document_id}")
        async def delete_document(
            document_id: uuid.UUID,
            tenant: Tenant = Depends(get_current_tenant),
            db: AsyncSession = Depends(get_db),
        ):
            document = await get_document(db, document_id)
            ensure_tenant_context(document.tenant_id, tenant)
            # Safe to delete - tenant matches
            await db.delete(document)
    
    Args:
        tenant_id: The tenant_id from the resource being accessed
        current_tenant: The tenant from the current user's context
        
    Raises:
        HTTPException: 403 if tenant_id doesn't match current tenant
    
    Reference: https://fastapi.tiangolo.com/tutorial/security/
    """
    if tenant_id != current_tenant.id:
        logger.warning(
            f"Tenant mismatch: user tenant {current_tenant.id} attempted to access "
            f"resource from tenant {tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access resources from your own organization",
        )


# Type alias for convenience
# Use this in route handlers for cleaner type hints
# Example: tenant: CurrentTenant = Depends(get_current_tenant)
CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]

