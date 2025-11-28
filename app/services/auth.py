import asyncio
import time
from typing import Optional
import httpx
from authlib.jose import jwt, JsonWebKey
from authlib.jose.errors import DecodeError, ExpiredTokenError, InvalidClaimError, BadSignatureError
from workos import WorkOSClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.api.v1.schemas.auth import ForgotPasswordRequest, ForgotPasswordResponse, LoginResponse, RefreshTokenResponse, SignupResponse, WorkOSAuthorizationRequest, WorkOSLoginRequest, WorkOSRefreshTokenRequest, WorkOSResetPasswordRequest, WorkOsVerifyEmailRequest, WorkOSUserResponse
from app.core.config import settings
from app.models.user import User
from app.services.tenant import TenantService

import logging

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        self.workos_client = WorkOSClient(
            api_key=settings.WORKOS_API_KEY,
            client_id=settings.WORKOS_CLIENT_ID
        )
        self.tenant_service = TenantService()
        # Cache JWKS to avoid repeated fetches (cache for 1 hour)
        self._jwks_cache: Optional[dict] = None
        self._jwks_cache_expiry: Optional[float] = None

    async def verify_email(self, verify_email_request: WorkOsVerifyEmailRequest):
        # Offload synchronous WorkOS call to thread pool to avoid blocking event loop
        # Reference: https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread
        response = await asyncio.to_thread(
            self.workos_client.user_management.authenticate_with_email_verification,
            code=verify_email_request.code,
            pending_authentication_token=verify_email_request.pending_authentication_token,
            ip_address=verify_email_request.ip_address,
            user_agent=verify_email_request.user_agent
        )
        return response

    async def login(self, login_request: WorkOSLoginRequest) -> LoginResponse:
        # Offload synchronous WorkOS call to thread pool to avoid blocking event loop
        response = await asyncio.to_thread(
            self.workos_client.user_management.authenticate_with_password,
            email=login_request.email,
            password=login_request.password,
            ip_address=login_request.ip_address,
            user_agent=login_request.user_agent
        )
        return LoginResponse(
            user=response.user,
            organization_id=response.organization_id,
            access_token=response.access_token,
            refresh_token=response.refresh_token
        )

    async def signup(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        organization_id: Optional[str] = None,
        create_tenant: bool = False,
        company_name: Optional[str] = None,
        company_domains: Optional[list[str]] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> SignupResponse:
        """
        Sign up a new user.
        
        Supports two flows:
        1. Join existing tenant: Provide organization_id
        2. Create new tenant: Set create_tenant=true with company_name (self-serve onboarding)
        
        Creates the user in WorkOS, adds them to the organization, and saves to database.
        User must verify their email before they can login.
        
        If create_tenant=true, the first user becomes admin of the new tenant.
        
        Args:
            db: Database session
            email: User email
            password: User password
            organization_id: WorkOS organization ID (required if create_tenant is false)
            create_tenant: If true, creates a new tenant and organization
            company_name: Company/tenant name (required if create_tenant is true)
            company_domains: Optional list of email domains for new organization
            first_name: Optional first name
            last_name: Optional last name
            
        Returns:
            SignupResponse with user info (no tokens - email verification required)
            
        Raises:
            IntegrityError: If user already exists in database (email conflict)
            BadRequestException: If user creation fails in WorkOS (e.g., email already exists)
            HTTPException: If organization_id is invalid or organization membership creation fails
        """
        # Check if user already exists in database BEFORE creating in WorkOS
        # This prevents creating orphaned users in WorkOS if DB insert fails
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            logger.warning(f"User already exists in database: {email}")
            # Raise IntegrityError to match database constraint violation behavior
            # This will be caught by the route handler and converted to 409 Conflict
            from sqlalchemy.exc import IntegrityError as SQLIntegrityError
            raise SQLIntegrityError(
                statement="INSERT INTO users",
                params=None,
                orig=Exception("duplicate key value violates unique constraint \"ix_users_email\"")
            )
        
        # Handle self-serve tenant creation flow
        # Note: We'll create the tenant after creating the user, so we can add the user to the org
        # For now, we'll set organization_id to None and handle it after user creation
        is_self_serve = create_tenant
        if is_self_serve:
            if not company_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="company_name is required when create_tenant is true"
                )
        
        # Validate organization_id is provided (unless creating new tenant)
        if not is_self_serve and not organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="organization_id is required. Either provide it directly or set create_tenant=true with company_name"
            )
        
        # Create user in WorkOS (only if not in database)
        create_user_payload = {
            "email": email,
            "password": password,
        }
        if first_name:
            create_user_payload["first_name"] = first_name
        if last_name:
            create_user_payload["last_name"] = last_name
        
        # Offload synchronous WorkOS call to thread pool
        workos_user = await asyncio.to_thread(
            self.workos_client.user_management.create_user,
            **create_user_payload
        )
        
        # Handle self-serve tenant creation: Create organization and tenant first
        if is_self_serve:
            try:
                # Provision tenant (creates WorkOS org + tenant record)
                tenant = await self.tenant_service.provision_tenant(
                    db=db,
                    name=company_name,
                    domains=company_domains,
                )
                organization_id = tenant.workos_organization_id
                logger.info(f"Provisioned new tenant {tenant.id} for self-serve signup: {company_name}")
            except Exception as tenant_error:
                # Clean up WorkOS user if tenant creation fails
                logger.error(f"Failed to provision tenant for self-serve signup: {tenant_error}")
                try:
                    await asyncio.to_thread(
                        self.workos_client.user_management.delete_user,
                        user_id=workos_user.id
                    )
                    logger.info(f"Cleaned up WorkOS user {workos_user.id} after tenant provisioning failure")
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up WorkOS user after tenant failure: {cleanup_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create tenant: {str(tenant_error)}"
                ) from tenant_error
        
        # Create organization membership in WorkOS
        # This links the user to the organization
        # Reference: https://workos.com/docs/reference/user-management/organization-memberships
        try:
            # If creating new tenant, first user gets admin role
            role_slug = "admin" if is_self_serve else None
            workos_org_membership = await asyncio.to_thread(
                self.workos_client.user_management.create_organization_membership,
                user_id=workos_user.id,
                organization_id=organization_id,
                role_slug=role_slug,
            )
            logger.info(
                f"Created organization membership for user {workos_user.id} in organization {organization_id} "
                f"with role: {role_slug or 'member'}"
            )
        except Exception as org_error:
            # If organization membership creation fails, clean up WorkOS user and tenant (if self-serve)
            logger.error(f"Failed to create organization membership: {org_error}")
            if is_self_serve:
                # Clean up tenant if it was created
                try:
                    await self.tenant_service.delete_tenant(db, tenant.id)
                    logger.info(f"Cleaned up tenant {tenant.id} after org membership failure")
                except Exception as tenant_cleanup_error:
                    logger.error(f"Failed to clean up tenant after org membership failure: {tenant_cleanup_error}")
            try:
                await asyncio.to_thread(
                    self.workos_client.user_management.delete_user,
                    user_id=workos_user.id
                )
                logger.info(f"Cleaned up WorkOS user {workos_user.id} after org membership failure")
            except Exception as cleanup_error:
                logger.error(f"Failed to clean up WorkOS user after org membership failure: {cleanup_error}")
            # Re-raise the original error
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to add user to organization: {str(org_error)}"
            ) from org_error
        
        # Get or create tenant by WorkOS organization ID (for existing organization flow)
        if not is_self_serve:
            try:
                tenant = await self.tenant_service.get_or_create_tenant_by_workos_organization_id(
                    db=db,
                    workos_organization_id=organization_id,
                    organization_name=getattr(workos_org_membership, 'organization_name', None),
                )
                logger.info(f"Resolved tenant {tenant.id} for WorkOS organization {organization_id}")
            except Exception as tenant_error:
                # If tenant creation fails, clean up WorkOS organization membership and user
                logger.error(f"Failed to get/create tenant: {tenant_error}")
                try:
                    # Delete organization membership first to prevent orphaned records
                    # Reference: https://workos.com/docs/reference/user-management/organization-memberships
                    if hasattr(workos_org_membership, 'id'):
                        await asyncio.to_thread(
                            self.workos_client.user_management.delete_organization_membership,
                            organization_membership_id=workos_org_membership.id
                        )
                        logger.info(f"Deleted organization membership {workos_org_membership.id} after tenant creation failure")
                    # Then delete the user
                    await asyncio.to_thread(
                        self.workos_client.user_management.delete_user,
                        user_id=workos_user.id
                    )
                    logger.info(f"Cleaned up WorkOS user {workos_user.id} after tenant creation failure")
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up WorkOS resources after tenant failure: {cleanup_error}")
                # Re-raise the original error
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create tenant: {str(tenant_error)}"
                ) from tenant_error
        
        # Create user in database with error handling
        # If DB insert fails, we need to clean up the WorkOS user to prevent orphaned accounts
        # Reference: https://workos.com/docs/reference/user-management/delete-user
        try:
            user = User(
                id=workos_user.id,
                email=workos_user.email,
                first_name=workos_user.first_name,
                last_name=workos_user.last_name,
                tenant_id=tenant.id,  # Set tenant_id from resolved tenant
            )
            db.add(user)
            await db.flush()
        except Exception as db_error:
            # Database operation failed - clean up WorkOS organization membership and user
            # This prevents users from being locked out if DB insert fails (race condition, connection issue, etc.)
            # and prevents orphaned organization memberships
            logger.warning(
                f"Database insert failed after WorkOS user creation for {email}. "
                f"Cleaning up WorkOS resources for user {workos_user.id}. Error: {db_error}"
            )
            try:
                # Delete organization membership first to prevent orphaned records
                # Reference: https://workos.com/docs/reference/user-management/organization-memberships
                if hasattr(workos_org_membership, 'id'):
                    await asyncio.to_thread(
                        self.workos_client.user_management.delete_organization_membership,
                        organization_membership_id=workos_org_membership.id
                    )
                    logger.info(f"Deleted organization membership {workos_org_membership.id} after DB failure")
                # Then delete the user
                await asyncio.to_thread(
                    self.workos_client.user_management.delete_user,
                    user_id=workos_user.id
                )
                logger.info(f"Successfully cleaned up WorkOS user {workos_user.id}")
            except Exception as cleanup_error:
                # Log cleanup failure but don't mask the original error
                logger.error(
                    f"Failed to clean up WorkOS resources for user {workos_user.id} after DB failure. "
                    f"Cleanup error: {cleanup_error}. Original error: {db_error}",
                    exc_info=True
                )
            # Re-raise the original database error
            raise
        
        logger.info(f"User created: {workos_user.id} ({email})")
        
        # Convert WorkOS user to response schema
        user_response = WorkOSUserResponse(
            object=workos_user.object,
            id=workos_user.id,
            email=workos_user.email,
            first_name=workos_user.first_name,
            last_name=workos_user.last_name,
            email_verified=workos_user.email_verified,
            profile_picture_url=workos_user.profile_picture_url,
            created_at=workos_user.created_at,
            updated_at=workos_user.updated_at,
        )
        
        return SignupResponse(user=user_response)

    async def forgot_password(self, forgot_password_request: ForgotPasswordRequest) -> ForgotPasswordResponse:
        
         # WorkOS generates token and sends email
        # The email will use the URL you configured in Dashboard → Redirects
        await asyncio.to_thread(
            self.workos_client.user_management.create_password_reset,
            email=forgot_password_request.email
        )
        
        # WorkOS automatically sends email with your configured URL
        # The URL will be: your-frontend.com/reset-password?token=...
        # NB: The WorkOS dashboard needs to be updated with the frontend password reset URL
        
        # Return generic success message (don't expose token/URL)
        return ForgotPasswordResponse(
            message="If an account exists with this email address, a password reset link has been sent."
        )

    async def reset_password(self, reset_password_request: WorkOSResetPasswordRequest) -> WorkOSUserResponse:
        """
        Reset a user's password.
        
        Args:
            reset_password_request: WorkOSResetPasswordRequest

        Returns:
            WorkOSUserResponse: User information
        """
        # Offload synchronous WorkOS call to thread pool to avoid blocking event loop
        response = await asyncio.to_thread(
            self.workos_client.user_management.reset_password,
            token=reset_password_request.token,
            new_password=reset_password_request.new_password
        )
        return WorkOSUserResponse(
            object=response.object,
            id=response.id,
            email=response.email,
            first_name=response.first_name,
            last_name=response.last_name,
            email_verified=response.email_verified,
            profile_picture_url=response.profile_picture_url,
            created_at=response.created_at,
            updated_at=response.updated_at,
        )

    # Generate OAuth2 authorization URL
    async def generate_oauth2_authorization_url(
        self, 
        authorization_request: WorkOSAuthorizationRequest
    ) -> str:
        """
        Generate OAuth2 authorization URL.
        
        Supports two patterns:
        1. AuthKit: provider="authkit" → Unified authentication interface
        2. SSO: connection_id="conn_xxx" → Direct provider connection
        
        Args:
            authorization_request: Request containing either provider or connection_id
            
        Returns:
            Authorization URL string
        """
        params = {
            "redirect_uri": authorization_request.redirect_uri,
        }
        
        # Add state if provided
        if authorization_request.state:
            params["state"] = authorization_request.state
        
        # Determine which pattern to use
        if authorization_request.provider:
            # AuthKit pattern
            params["provider"] = authorization_request.provider
        elif authorization_request.connection_id:
            # SSO pattern
            params["connection_id"] = authorization_request.connection_id
        
        # Offload synchronous WorkOS call to thread pool to avoid blocking event loop
        authorization_url = await asyncio.to_thread(
            self.workos_client.user_management.get_authorization_url,
            **params
        )
        return authorization_url


    async def oauth2_callback(
        self, 
        code: str
    ) -> LoginResponse:
        """
        Exchange a OAuth2 code for access token and refresh token.
        
        Args:
            code: OAuth2 code
            
        Returns:
            LoginResponse: Access token and refresh token
        """
        # Offload synchronous WorkOS call to thread pool to avoid blocking event loop
        response = await asyncio.to_thread(
            self.workos_client.user_management.authenticate_with_code,
            code=code
        )
        return LoginResponse(
            user=response.user,
            organization_id=response.organization_id,
            access_token=response.access_token,
            refresh_token=response.refresh_token
        )

    async def verify_session(self, access_token: str) -> dict:
        """
        Verify a WorkOS JWT access token with full signature verification.
        
        Uses WorkOS JWKS to verify the token signature. This ensures the token
        is authentic and hasn't been tampered with.
        
        Reference: 
        - https://workos.com/docs/reference/authkit/session-tokens/access-token
        - https://workos.com/docs/reference/authkit/session-tokens/jwks
        
        Args:
            access_token: JWT token from WorkOS
            
        Returns:
            Dict with user information from verified token:
            - user_id: User ID (sub claim)
            - session_id: Session ID (sid claim)
            - organization_id: Organization ID (org_id claim)
            - role: User role (role claim)
            - roles: Array of roles (roles claim)
            - permissions: Array of permissions (permissions claim)
            - entitlements: Array of entitlements (entitlements claim)
            - exp: Expiration timestamp
            - iat: Issued at timestamp
            
        Raises:
            ValueError: If token is invalid, expired, or signature verification fails
        """
        try:
            # Get JWKS URL from WorkOS SDK
            # Reference: https://workos.com/docs/reference/authkit/session-tokens/jwks
            # get_jwks_url() uses the client_id from the WorkOSClient initialization
            jwks_url = await asyncio.to_thread(
                self.workos_client.user_management.get_jwks_url
            )
            
            # Fetch JWKS (with caching to avoid repeated API calls)
            current_time = time.time()
            if not self._jwks_cache or (self._jwks_cache_expiry and current_time > self._jwks_cache_expiry):
                logger.debug(f"Fetching JWKS from: {jwks_url}")
                async with httpx.AsyncClient() as client:
                    response = await client.get(jwks_url, timeout=10.0)
                    response.raise_for_status()
                    self._jwks_cache = response.json()
                    # Cache for 1 hour (JWKS keys don't change often)
                    self._jwks_cache_expiry = current_time + 3600
                    logger.debug(f"JWKS fetched and cached. Keys: {len(self._jwks_cache.get('keys', []))}")
            
            # Create JWK set from JWKS
            # authlib handles parsing the JWKS and selecting the correct key
            jwk_set = JsonWebKey.import_key_set(self._jwks_cache)
            
            # Verify and decode the JWT
            # jwt.decode() verifies the signature using the correct key from JWKS (based on 'kid' in header)
            # However, it does NOT validate expiration/claims - that requires claims.validate()
            claims = jwt.decode(
                access_token,
                jwk_set,
                claims_options={
                    "exp": {"essential": True},
                    "iat": {"essential": True}
                }
            )
            
            # CRITICAL: Validate claims (expiration, issued at, etc.)
            # Without this, expired tokens would be accepted!
            claims.validate()
            
            logger.debug(f"Token verified successfully. User: {claims.get('sub')}")
            
            # Extract user information from verified token
            # Reference: https://workos.com/docs/reference/authkit/session-tokens/access-token
            return {
                'user_id': claims.get('sub'),              # User ID (subject)
                'session_id': claims.get('sid'),           # Session ID
                'organization_id': claims.get('org_id'),  # Organization ID
                'role': claims.get('role'),                # User role (e.g., "member", "admin")
                'roles': claims.get('roles', []),         # Array of roles
                'permissions': claims.get('permissions', []), # Permissions array
                'entitlements': claims.get('entitlements', []), # Entitlements array
                'exp': claims.get('exp'),
                'iat': claims.get('iat'),
            }
            
        except ExpiredTokenError:
            logger.warning("Token has expired")
            raise ValueError("Token has expired")
        except BadSignatureError:
            logger.warning("Invalid token signature")
            raise ValueError("Invalid token signature - token may have been tampered with")
        except DecodeError as e:
            logger.warning(f"Failed to decode token: {e}")
            raise ValueError(f"Invalid token format: {e}")
        except InvalidClaimError as e:
            logger.warning(f"Invalid token claim: {e}")
            raise ValueError(f"Invalid token claim: {e}")
        except Exception as e:
            logger.error(f"Error verifying session: {type(e).__name__}: {e}", exc_info=True)
            raise ValueError(f"Token verification failed: {str(e)}")


    # refresh token
    async def refresh_token(self, refresh_token_request: WorkOSRefreshTokenRequest) -> RefreshTokenResponse:
        """
        Refresh a WorkOS JWT access token.
        
        Args:
            refresh_token_request: WorkOSRefreshTokenRequest
            
        Returns:
            RefreshTokenResponse: Access token and refresh token
        """
        # Offload synchronous WorkOS call to thread pool to avoid blocking event loop
        response = await asyncio.to_thread(
            self.workos_client.user_management.authenticate_with_refresh_token,
            refresh_token=refresh_token_request.refresh_token,
            ip_address=refresh_token_request.ip_address,
            user_agent=refresh_token_request.user_agent
        )
        return RefreshTokenResponse(
            access_token=response.access_token,
            refresh_token=response.refresh_token
        )

