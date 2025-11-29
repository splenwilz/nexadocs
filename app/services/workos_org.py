"""
Helpers for WorkOS Organization lifecycle management.
Reference: https://workos.com/docs/reference/authkit/authentication-errors/organization-authentication-required-error
"""
import asyncio
import logging
from typing import Sequence

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class WorkOSConfigError(Exception):
    """Raised when WorkOS configuration is missing or invalid."""
    pass


class WorkOSOrganizationService:
    """
    Minimal client for WorkOS Organization APIs.
    Uses direct HTTP calls because the official SDK does not expose
    every endpoint we need (per docs linked above).
    """

    _BASE_URL = "https://api.workos.com/organizations"

    def __init__(self) -> None:
        if not settings.WORKOS_API_KEY:
            raise WorkOSConfigError("WORKOS_API_KEY must be set to provision organizations")
        self._api_key = settings.WORKOS_API_KEY

    async def create_organization(
        self,
        name: str,
        domains: Sequence[str] | None = None,
    ) -> dict:
        """
        Create a WorkOS organization with optional domains.

        Docs: https://workos.com/docs/reference/authkit/authentication-errors/organization-authentication-required-error#create-an-organization
        """
        payload: dict = {"name": name}
        if domains:
            # WorkOS API expects "domain_data" (not "domains") with state "pending" (not "unverified")
            # Reference: https://workos.com/docs/reference/authkit/authentication-errors/organization-authentication-required-error#create-an-organization
            payload["domain_data"] = [
                {"domain": domain.strip().lower(), "state": "pending"}
                for domain in domains
                if domain.strip()
            ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(self._BASE_URL, json=payload, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                logger.exception("WorkOS organization creation failed with non-2xx response")
                raise
            return response.json()

    async def delete_organization(self, organization_id: str) -> None:
        """
        Delete a WorkOS organization.

        Reference: https://workos.com/docs/reference/authkit/authentication-errors/organization-authentication-required-error
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(
                f"{self._BASE_URL}/{organization_id}",
                headers=headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                logger.exception("WorkOS organization deletion failed with non-2xx response")
                raise

    async def create_organization_membership(
        self,
        user_id: str,
        organization_id: str,
        role_slug: str = "admin",
    ) -> dict:
        """
        Create an organization membership for a user with a specific role.

        Reference: https://workos.com/docs/reference/user-management/organization-memberships
        """
        payload = {
            "user_id": user_id,
            "organization_id": organization_id,
            "role_slug": role_slug,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.workos.com/user_management/organization_memberships",
                json=payload,
                headers=headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                logger.exception("WorkOS organization membership creation failed with non-2xx response")
                raise
            return response.json()

