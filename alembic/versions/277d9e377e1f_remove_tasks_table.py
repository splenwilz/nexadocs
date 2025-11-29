"""remove_tasks_table

Revision ID: 277d9e377e1f
Revises: 62b64a023e16
Create Date: 2025-11-29 14:39:33.980407

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '277d9e377e1f'
down_revision: Union[str, Sequence[str], None] = '62b64a023e16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop tasks table and its indexes
    op.drop_index(op.f('ix_tasks_title'), table_name='tasks', if_exists=True)
    op.drop_index(op.f('ix_tasks_id'), table_name='tasks', if_exists=True)
    op.drop_table('tasks')


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate tasks table (for rollback purposes)
    op.create_table('tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('completed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_id'), 'tasks', ['id'], unique=False)
    op.create_index(op.f('ix_tasks_title'), 'tasks', ['title'], unique=False)
