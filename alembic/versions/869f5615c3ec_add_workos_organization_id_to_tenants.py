"""add_workos_organization_id_to_tenants

Revision ID: 869f5615c3ec
Revises: 07d4be112979
Create Date: 2025-11-28 04:04:55.750662

This migration adds workos_organization_id to the tenants table.
This field maps WorkOS organizations to our tenant model, enabling
automatic tenant creation when users sign up with an organization_id.

Reference: https://alembic.sqlalchemy.org/en/latest/tutorial.html
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '869f5615c3ec'
down_revision: Union[str, Sequence[str], None] = '07d4be112979'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add workos_organization_id column to tenants table.
    
    This column:
    - Maps WorkOS organization IDs to our tenant model
    - Is nullable (existing tenants don't have WorkOS orgs)
    - Is unique (one tenant per WorkOS organization)
    - Is indexed for fast lookups
    """
    op.add_column(
        'tenants',
        sa.Column(
            'workos_organization_id',
            sa.String(length=255),
            nullable=True,  # Nullable for existing tenants
            comment='WorkOS organization ID that maps to this tenant',
        )
    )
    
    # Create unique index on workos_organization_id
    # This ensures one tenant per WorkOS organization
    op.create_index(
        'ix_tenants_workos_organization_id',
        'tenants',
        ['workos_organization_id'],
        unique=True,
    )


def downgrade() -> None:
    """
    Remove workos_organization_id column from tenants table.
    """
    # Drop index first
    op.drop_index('ix_tenants_workos_organization_id', table_name='tenants')
    
    # Drop column
    op.drop_column('tenants', 'workos_organization_id')
