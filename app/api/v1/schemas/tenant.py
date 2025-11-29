"""
Tenant API schemas for request/response models
Reference: https://fastapi.tiangolo.com/tutorial/body/
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class TenantBase(BaseModel):
    """
    Base schema with common Tenant fields
    Used as base for create/update schemas
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Tenant organization name",
    )
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="URL-friendly tenant identifier (e.g., 'acme-corp')",
    )


class TenantCreate(TenantBase):
    """
    Schema for creating a new tenant (admin only)
    
    Attributes:
        name: Tenant organization name (required)
        slug: URL-friendly identifier (required, must be unique)
        is_active: Whether tenant is active (default: True)
    
    Reference: https://fastapi.tiangolo.com/tutorial/body/
    """
    is_active: bool = Field(
        default=True,
        description="Whether the tenant is active (can access system)",
    )
    
    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """
        Validate slug format: lowercase, alphanumeric, hyphens only
        
        Slugs must be URL-safe and follow common conventions:
        - Lowercase only
        - Alphanumeric characters and hyphens
        - No spaces or special characters
        
        Reference: https://docs.pydantic.dev/latest/concepts/validators/
        """
        v = v.lower().strip()
        
        if not v:
            raise ValueError("Slug cannot be empty")
        
        # Check for valid characters: lowercase letters, numbers, hyphens
        if not all(c.isalnum() or c == '-' for c in v):
            raise ValueError(
                "Slug can only contain lowercase letters, numbers, and hyphens"
            )
        
        # Cannot start or end with hyphen
        if v.startswith('-') or v.endswith('-'):
            raise ValueError("Slug cannot start or end with a hyphen")
        
        # Must start with a letter or number
        if not v[0].isalnum():
            raise ValueError("Slug must start with a letter or number")
        
        return v


class TenantUpdate(BaseModel):
    """
    Schema for updating a tenant (admin only)
    
    All fields are optional for partial updates.
    Only provided fields will be updated.
    
    Attributes:
        name: Tenant organization name (optional)
        slug: URL-friendly identifier (optional, must be unique if provided)
        is_active: Whether tenant is active (optional)
    
    Reference: https://fastapi.tiangolo.com/tutorial/body/
    """
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Tenant organization name",
    )
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="URL-friendly tenant identifier",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether the tenant is active",
    )
    
    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        """Validate slug format if provided"""
        if v is None:
            return v
        
        v = v.lower().strip()
        
        if not v:
            raise ValueError("Slug cannot be empty")
        
        if not all(c.isalnum() or c == '-' for c in v):
            raise ValueError(
                "Slug can only contain lowercase letters, numbers, and hyphens"
            )
        
        if v.startswith('-') or v.endswith('-'):
            raise ValueError("Slug cannot start or end with a hyphen")
        
        if not v[0].isalnum():
            raise ValueError("Slug must start with a letter or number")
        
        return v


class TenantProvisionRequest(BaseModel):
    """
    Schema for provisioning a new tenant with WorkOS organization
    
    This endpoint automatically creates a WorkOS organization and links it
    to a new tenant. The slug is auto-generated from the name.
    
    Attributes:
        name: Tenant organization name (required)
        domains: Optional list of email domains to associate with the organization
    
    Reference: https://workos.com/docs/reference/authkit/authentication-errors/organization-authentication-required-error#create-an-organization
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Tenant organization name",
    )
    domains: Optional[list[str]] = Field(
        None,
        description="Optional list of email domains (e.g., ['example.com']) to associate with the WorkOS organization. Domains are created in 'unverified' state.",
    )


class TenantResponse(BaseModel):
    """
    Schema for tenant response
    
    Includes all tenant fields returned from the API.
    Used for GET endpoints.
    
    Attributes:
        id: Tenant UUID
        name: Tenant organization name
        slug: URL-friendly identifier
        workos_organization_id: WorkOS organization ID (if provisioned via automated flow)
        is_active: Whether tenant is active
        created_at: Timestamp when tenant was created
        updated_at: Timestamp when tenant was last updated
    
    Reference: https://fastapi.tiangolo.com/tutorial/response-model/
    """
    id: uuid.UUID = Field(..., description="Tenant UUID")
    name: str = Field(..., description="Tenant organization name")
    slug: str = Field(..., description="URL-friendly tenant identifier")
    workos_organization_id: Optional[str] = Field(
        None,
        description="WorkOS organization ID (format: org_01E4ZCR3C56J083X43JQXF3JK5)",
    )
    is_active: bool = Field(..., description="Whether tenant is active")
    created_at: datetime = Field(..., description="Timestamp when tenant was created")
    updated_at: datetime = Field(..., description="Timestamp when tenant was last updated")
    
    # Enable Pydantic to read from SQLAlchemy models
    # Reference: https://docs.pydantic.dev/latest/concepts/models/#orm-mode-aka-arbitrary-class-instances
    model_config = ConfigDict(from_attributes=True)

