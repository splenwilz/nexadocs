"""
Tenant management API routes (admin only)
Handles CRUD operations for tenants
Reference: https://fastapi.tiangolo.com/tutorial/bigger-applications/
"""
import logging
import uuid
from typing import List
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.admin import get_current_admin_user
from app.core.tenant import get_tenant_by_id
from app.models.tenant import Tenant
from app.api.v1.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantProvisionRequest
from app.api.v1.schemas.auth import WorkOSUserResponse
from app.services.tenant import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tenants",
    tags=["tenants"],
)


@router.post(
    "",
    response_model=TenantResponse,
    summary="Create tenant",
    description="Create a new tenant (admin only)",
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    tenant_data: TenantCreate,
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Create a new tenant (admin only)
    
    Creates a new tenant organization with the specified name and slug.
    The slug must be unique across all tenants.
    
    Args:
        tenant_data: Tenant creation data (name, slug, is_active)
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        TenantResponse: Created tenant with all fields
        
    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 409 if slug already exists
        HTTPException: 400 for validation errors
    """
    tenant_service = TenantService()
    
    try:
        tenant = await tenant_service.create_tenant(db, tenant_data)
        await db.commit()  # Commit transaction
        
        logger.info(f"Admin {admin_user.id} created tenant: {tenant.id} ({tenant.name})")
        return TenantResponse.model_validate(tenant)
        
    except IntegrityError as e:
        await db.rollback()
        
        # Check if error is due to duplicate slug
        if "slug" in str(e.orig).lower() or "unique" in str(e.orig).lower():
            logger.warning(f"Duplicate slug attempted: {tenant_data.slug}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tenant with slug '{tenant_data.slug}' already exists",
            ) from e
        
        # Generic integrity error
        logger.error(f"Integrity error creating tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create tenant due to data conflict",
        ) from e
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error creating tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the tenant",
        ) from e


@router.post(
    "/provision",
    response_model=TenantResponse,
    summary="Provision tenant with WorkOS organization",
    description="Automatically create a new tenant and WorkOS organization (admin only)",
    status_code=status.HTTP_201_CREATED,
)
async def provision_tenant(
    provision_data: TenantProvisionRequest,
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Provision a new tenant with automated WorkOS organization creation (admin only)
    
    This endpoint automates the tenant onboarding process by:
    1. Creating a WorkOS organization with the provided name and optional domains
    2. Creating a tenant record in our database linked to the WorkOS organization
    3. Auto-generating a unique slug from the tenant name
    
    This eliminates the need to manually create WorkOS organizations and copy IDs.
    
    Args:
        provision_data: Tenant provisioning data (name, optional domains)
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        TenantResponse: Created tenant with WorkOS organization ID
        
    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 500 if WorkOS organization creation fails
        HTTPException: 500 if tenant creation fails
        
    Reference: https://workos.com/docs/reference/authkit/authentication-errors/organization-authentication-required-error#create-an-organization
    """
    tenant_service = TenantService()
    workos_org_service = tenant_service.workos_orgs
    
    try:
        # Provision tenant (creates WorkOS org + tenant record)
        tenant = await tenant_service.provision_tenant(
            db,
            name=provision_data.name,
            domains=provision_data.domains,
        )
        
        # Automatically add the admin user to the newly provisioned organization with admin role
        # This allows the admin to access the tenant they just created
        # Reference: https://workos.com/docs/reference/user-management/organization-memberships
        try:
            await workos_org_service.create_organization_membership(
                user_id=admin_user.id,
                organization_id=tenant.workos_organization_id,
                role_slug="admin",
            )
            logger.info(
                f"Added admin {admin_user.id} to provisioned organization {tenant.workos_organization_id} with admin role"
            )
        except Exception as membership_error:
            # Log but don't fail the tenant creation if membership creation fails
            # The tenant is already created, admin can be added manually later
            logger.warning(
                f"Failed to add admin {admin_user.id} to organization {tenant.workos_organization_id}: {membership_error}. "
                f"Tenant was created successfully, but admin membership needs to be added manually."
            )
        
        await db.commit()  # Commit transaction
        
        logger.info(
            f"Admin {admin_user.id} provisioned tenant: {tenant.id} ({tenant.name}) "
            f"with WorkOS org: {tenant.workos_organization_id}"
        )
        return TenantResponse.model_validate(tenant)
        
    except httpx.HTTPStatusError as e:
        await db.rollback()
        logger.error(f"WorkOS organization creation failed: {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create WorkOS organization: {e.response.text}",
        ) from e
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error provisioning tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while provisioning the tenant",
        ) from e


@router.get(
    "",
    response_model=List[TenantResponse],
    summary="List tenants",
    description="Get a list of all tenants (admin only)",
)
async def list_tenants(
    skip: int = Query(0, ge=0, description="Number of tenants to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tenants to return"),
    include_inactive: bool = Query(False, description="Include inactive tenants"),
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> List[TenantResponse]:
    """
    Get a list of all tenants (admin only)
    
    Returns paginated list of tenants. By default, only active tenants
    are returned. Set include_inactive=true to include inactive tenants.
    
    Args:
        skip: Number of tenants to skip (for pagination)
        limit: Maximum number of tenants to return
        include_inactive: Whether to include inactive tenants
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        List[TenantResponse]: List of tenants
        
    Raises:
        HTTPException: 403 if user is not admin
    """
    tenant_service = TenantService()
    tenants = await tenant_service.get_tenants(
        db,
        skip=skip,
        limit=limit,
        include_inactive=include_inactive,
    )
    
    return [TenantResponse.model_validate(tenant) for tenant in tenants]


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get tenant",
    description="Get a tenant by ID (admin only)",
)
async def get_tenant(
    tenant_id: uuid.UUID,
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Get a tenant by ID (admin only)
    
    Args:
        tenant_id: UUID of the tenant to fetch
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        TenantResponse: Tenant details
        
    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 404 if tenant not found
    """
    tenant_service = TenantService()
    tenant = await tenant_service.get_tenant(db, tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )
    
    return TenantResponse.model_validate(tenant)


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Update tenant",
    description="Update a tenant by ID (admin only)",
    status_code=status.HTTP_200_OK,
)
async def update_tenant(
    tenant_id: uuid.UUID,
    tenant_data: TenantUpdate,
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Update a tenant by ID (admin only)
    
    Performs partial update - only provided fields will be updated.
    
    Args:
        tenant_id: UUID of the tenant to update
        tenant_data: Tenant update data (only provided fields will be updated)
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        TenantResponse: Updated tenant
        
    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 404 if tenant not found
        HTTPException: 409 if slug already exists
    """
    tenant_service = TenantService()
    
    try:
        tenant = await tenant_service.update_tenant(db, tenant_id, tenant_data)
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )
        
        await db.commit()  # Commit transaction
        
        logger.info(f"Admin {admin_user.id} updated tenant: {tenant.id} ({tenant.name})")
        return TenantResponse.model_validate(tenant)
        
    except IntegrityError as e:
        await db.rollback()
        
        # Check if error is due to duplicate slug
        if "slug" in str(e.orig).lower() or "unique" in str(e.orig).lower():
            logger.warning(f"Duplicate slug attempted: {tenant_data.slug}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tenant with slug '{tenant_data.slug}' already exists",
            ) from e
        
        # Generic integrity error
        logger.error(f"Integrity error updating tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update tenant due to data conflict",
        ) from e
    except HTTPException:
        # Re-raise HTTP exceptions (already formatted)
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error updating tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the tenant",
        ) from e


@router.delete(
    "/{tenant_id}",
    summary="Delete tenant",
    description="Delete a tenant by ID (admin only). WARNING: This permanently deletes all tenant data.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "Tenant not found"},
        204: {"description": "Tenant deleted successfully"},
    },
)
async def delete_tenant(
    tenant_id: uuid.UUID,
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a tenant by ID (admin only)
    
    WARNING: This is a hard delete that permanently removes:
    - The tenant
    - All users in the tenant (cascade)
    - All documents in the tenant (cascade)
    - All conversations and messages (cascade)
    - All validated answers (cascade)
    
    For production, consider using deactivate_tenant endpoint instead
    (soft delete that preserves data).
    
    Args:
        tenant_id: UUID of the tenant to delete
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        None (204 No Content on success)
        
    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 404 if tenant not found
    """
    tenant_service = TenantService()
    
    try:
        deleted = await tenant_service.delete_tenant(db, tenant_id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )
        
        await db.commit()  # Commit transaction
        
        logger.warning(f"Admin {admin_user.id} deleted tenant: {tenant_id}")
        return None
        
    except HTTPException:
        # Re-raise HTTP exceptions (already formatted)
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error deleting tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting the tenant",
        ) from e


@router.post(
    "/{tenant_id}/deactivate",
    response_model=TenantResponse,
    summary="Deactivate tenant",
    description="Deactivate a tenant (soft delete - preserves data)",
    status_code=status.HTTP_200_OK,
)
async def deactivate_tenant(
    tenant_id: uuid.UUID,
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Deactivate a tenant (soft delete - admin only)
    
    Sets is_active=False, preventing tenant users from accessing the system.
    All data is preserved for potential reactivation.
    
    This is safer than hard delete and recommended for production.
    
    Args:
        tenant_id: UUID of the tenant to deactivate
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        TenantResponse: Deactivated tenant
        
    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 404 if tenant not found
    """
    tenant_service = TenantService()
    
    try:
        tenant = await tenant_service.deactivate_tenant(db, tenant_id)
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )
        
        await db.commit()  # Commit transaction
        
        logger.info(f"Admin {admin_user.id} deactivated tenant: {tenant.id} ({tenant.name})")
        return TenantResponse.model_validate(tenant)
        
    except HTTPException:
        # Re-raise HTTP exceptions (already formatted)
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error deactivating tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deactivating the tenant",
        ) from e


@router.post(
    "/{tenant_id}/activate",
    response_model=TenantResponse,
    summary="Activate tenant",
    description="Activate a previously deactivated tenant",
    status_code=status.HTTP_200_OK,
)
async def activate_tenant(
    tenant_id: uuid.UUID,
    admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Activate a tenant (admin only)
    
    Sets is_active=True, allowing tenant users to access the system again.
    Used to reactivate a previously deactivated tenant.
    
    Args:
        tenant_id: UUID of the tenant to activate
        admin_user: Authenticated admin user (injected via dependency)
        db: Database session (injected via dependency)
        
    Returns:
        TenantResponse: Activated tenant
        
    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 404 if tenant not found
    """
    tenant_service = TenantService()
    
    try:
        tenant = await tenant_service.activate_tenant(db, tenant_id)
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )
        
        await db.commit()  # Commit transaction
        
        logger.info(f"Admin {admin_user.id} activated tenant: {tenant.id} ({tenant.name})")
        return TenantResponse.model_validate(tenant)
        
    except HTTPException:
        # Re-raise HTTP exceptions (already formatted)
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error activating tenant: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while activating the tenant",
        ) from e

