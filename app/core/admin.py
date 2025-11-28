"""
Admin authentication dependencies
Checks if user has admin role from WorkOS JWT claims
Reference: https://fastapi.tiangolo.com/tutorial/dependencies/
"""
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.dependencies import get_current_user, get_auth_service
from app.api.v1.schemas.auth import WorkOSUserResponse

logger = logging.getLogger(__name__)

# HTTPBearer for extracting Bearer token
security = HTTPBearer()


async def get_current_admin_user(
    current_user: WorkOSUserResponse = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> WorkOSUserResponse:
    """
    Dependency to verify the current user has admin role.
    
    Checks the JWT token for admin role. Admin users can:
    - Create, update, delete tenants
    - View all tenants (including inactive)
    - Manage users across tenants
    - Review and correct answers
    
    Usage:
        @router.post("/admin/tenants")
        async def create_tenant(
            admin_user: WorkOSUserResponse = Depends(get_current_admin_user),
            tenant_data: TenantCreate,
            db: AsyncSession = Depends(get_db),
        ):
            # Only admins can access this endpoint
            pass
    
    Args:
        current_user: Authenticated user (from get_current_user dependency)
        credentials: HTTPAuthorizationCredentials containing the Bearer token
        
    Returns:
        WorkOSUserResponse: The authenticated admin user
        
    Raises:
        HTTPException: 403 if user is not an admin
        
    Reference: https://fastapi.tiangolo.com/tutorial/dependencies/
    """
    auth_service = get_auth_service()
    
    try:
        # Extract token to verify session and get role claims
        access_token = credentials.credentials
        
        # Verify session and get role information from JWT claims
        # Reference: https://workos.com/docs/reference/authkit/session-tokens/access-token
        session_data = await auth_service.verify_session(access_token)
        
        # Check for admin role
        # WorkOS provides role in claims as 'role' (string) or 'roles' (array)
        role = session_data.get('role')
        roles = session_data.get('roles', [])
        
        # Check if user has admin role
        # Support both 'role' (string) and 'roles' (array) formats
        is_admin = (
            role == 'admin' or
            'admin' in roles or
            role == 'Admin' or  # Case-insensitive check
            'Admin' in roles
        )
        
        if not is_admin:
            logger.warning(f"Non-admin user {current_user.id} attempted to access admin endpoint")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required. You do not have permission to perform this action.",
            )
        
        logger.debug(f"Admin access granted to user {current_user.id} ({current_user.email})")
        return current_user
        
    except HTTPException:
        # Re-raise HTTP exceptions (already formatted)
        raise
    except Exception as e:
        logger.error(f"Error verifying admin access: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Failed to verify admin access",
        ) from e

