"""Initial migration: Add multi-tenant models

Revision ID: 07d4be112979
Revises: 
Create Date: 2025-11-28 02:18:12.871387

This migration creates:
- tenants table (multi-tenant foundation)
- Updates users table with tenant_id foreign key
- documents table (PDF storage and processing)
- conversations table (chat sessions)
- messages table (chat messages)
- validated_answers table (admin corrections)

Reference: https://alembic.sqlalchemy.org/en/latest/tutorial.html
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '07d4be112979'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema: Create all multi-tenant tables and update users table.
    
    Order matters:
    1. Create tenants table first (no dependencies)
    2. Add tenant_id to users table (depends on tenants)
    3. Create documents table (depends on tenants)
    4. Create conversations table (depends on tenants and users)
    5. Create messages table (depends on conversations)
    6. Create validated_answers table (depends on tenants and messages)
    """
    # Create tenants table
    # This is the foundation for multi-tenant architecture
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='tenants_pkey'),
    )
    
    # Create indexes for tenants table
    # Indexes improve query performance for common lookups
    op.create_index('ix_tenants_id', 'tenants', ['id'], unique=False)
    op.create_index('ix_tenants_name', 'tenants', ['name'], unique=False)
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)  # Unique index for slug
    op.create_index('ix_tenants_is_active', 'tenants', ['is_active'], unique=False)
    
    # Create users table
    # This table stores user information from WorkOS
    # Note: tenant_id is included in the table creation (nullable initially for existing users)
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),  # Nullable initially
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='users_pkey'),
    )
    
    # Create indexes for users table
    op.create_index('ix_users_id', 'users', ['id'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)  # Email unique globally (can be changed later)
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'], unique=False)
    
    # Create foreign key constraint for users.tenant_id -> tenants.id
    # CASCADE delete: if tenant is deleted, users are also deleted
    # Note: PostgreSQL automatically creates an index for foreign keys,
    # so we don't need to create ix_users_tenant_id explicitly
    op.create_foreign_key(
        'fk_users_tenant_id_tenants',
        'users', 'tenants',
        ['tenant_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Note: Index on tenant_id is automatically created by PostgreSQL for the foreign key
    # If you need a custom index name, you can create it explicitly, but it's not necessary
    
    # Create documents table
    # Stores uploaded PDF files and processing metadata
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False, server_default='application/pdf'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.String(length=2000), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='documents_pkey'),
        sa.UniqueConstraint('file_path', name='documents_file_path_key'),
    )
    
    # Create foreign key for documents.tenant_id -> tenants.id
    op.create_foreign_key(
        'fk_documents_tenant_id_tenants',
        'documents', 'tenants',
        ['tenant_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes for documents table
    op.create_index('ix_documents_id', 'documents', ['id'], unique=False)
    op.create_index('ix_documents_tenant_id', 'documents', ['tenant_id'], unique=False)
    op.create_index('ix_documents_filename', 'documents', ['filename'], unique=False)
    op.create_index('ix_documents_file_path', 'documents', ['file_path'], unique=True)
    op.create_index('ix_documents_status', 'documents', ['status'], unique=False)
    
    # Create conversations table
    # Stores chat sessions between users and AI assistant
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='conversations_pkey'),
    )
    
    # Create foreign keys for conversations
    op.create_foreign_key(
        'fk_conversations_tenant_id_tenants',
        'conversations', 'tenants',
        ['tenant_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_conversations_user_id_users',
        'conversations', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes for conversations table
    op.create_index('ix_conversations_id', 'conversations', ['id'], unique=False)
    op.create_index('ix_conversations_tenant_id', 'conversations', ['tenant_id'], unique=False)
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'], unique=False)
    op.create_index('ix_conversations_title', 'conversations', ['title'], unique=False)
    op.create_index('ix_conversations_created_at', 'conversations', ['created_at'], unique=False)
    op.create_index('ix_conversations_updated_at', 'conversations', ['updated_at'], unique=False)
    
    # Create messages table
    # Stores individual messages in conversations
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('citations', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='messages_pkey'),
    )
    
    # Create foreign key for messages.conversation_id -> conversations.id
    op.create_foreign_key(
        'fk_messages_conversation_id_conversations',
        'messages', 'conversations',
        ['conversation_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes for messages table
    op.create_index('ix_messages_id', 'messages', ['id'], unique=False)
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False)
    op.create_index('ix_messages_role', 'messages', ['role'], unique=False)
    op.create_index('ix_messages_created_at', 'messages', ['created_at'], unique=False)
    
    # Create validated_answers table
    # Stores admin-corrected answers for training/validation
    op.create_table(
        'validated_answers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_question', sa.Text(), nullable=False),
        sa.Column('original_answer', sa.Text(), nullable=False),
        sa.Column('corrected_answer', sa.Text(), nullable=False),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='validated_answers_pkey'),
        sa.UniqueConstraint('message_id', name='validated_answers_message_id_key'),
    )
    
    # Create foreign keys for validated_answers
    op.create_foreign_key(
        'fk_validated_answers_tenant_id_tenants',
        'validated_answers', 'tenants',
        ['tenant_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_validated_answers_message_id_messages',
        'validated_answers', 'messages',
        ['message_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes for validated_answers table
    op.create_index('ix_validated_answers_id', 'validated_answers', ['id'], unique=False)
    op.create_index('ix_validated_answers_tenant_id', 'validated_answers', ['tenant_id'], unique=False)
    op.create_index('ix_validated_answers_message_id', 'validated_answers', ['message_id'], unique=True)
    op.create_index('ix_validated_answers_original_question', 'validated_answers', ['original_question'], unique=False)
    op.create_index('ix_validated_answers_created_at', 'validated_answers', ['created_at'], unique=False)


def downgrade() -> None:
    """
    Downgrade schema: Drop all multi-tenant tables and remove tenant_id from users.
    
    Order matters (reverse of upgrade):
    1. Drop validated_answers table
    2. Drop messages table
    3. Drop conversations table
    4. Drop documents table
    5. Remove tenant_id from users table
    6. Drop tenants table
    """
    # Drop validated_answers table
    op.drop_index('ix_validated_answers_created_at', table_name='validated_answers')
    op.drop_index('ix_validated_answers_original_question', table_name='validated_answers')
    op.drop_index('ix_validated_answers_message_id', table_name='validated_answers')
    op.drop_index('ix_validated_answers_tenant_id', table_name='validated_answers')
    op.drop_index('ix_validated_answers_id', table_name='validated_answers')
    op.drop_table('validated_answers')
    
    # Drop messages table
    op.drop_index('ix_messages_created_at', table_name='messages')
    op.drop_index('ix_messages_role', table_name='messages')
    op.drop_index('ix_messages_conversation_id', table_name='messages')
    op.drop_index('ix_messages_id', table_name='messages')
    op.drop_table('messages')
    
    # Drop conversations table
    op.drop_index('ix_conversations_updated_at', table_name='conversations')
    op.drop_index('ix_conversations_created_at', table_name='conversations')
    op.drop_index('ix_conversations_title', table_name='conversations')
    op.drop_index('ix_conversations_user_id', table_name='conversations')
    op.drop_index('ix_conversations_tenant_id', table_name='conversations')
    op.drop_index('ix_conversations_id', table_name='conversations')
    op.drop_table('conversations')
    
    # Drop documents table
    op.drop_index('ix_documents_status', table_name='documents')
    op.drop_index('ix_documents_file_path', table_name='documents')
    op.drop_index('ix_documents_filename', table_name='documents')
    op.drop_index('ix_documents_tenant_id', table_name='documents')
    op.drop_index('ix_documents_id', table_name='documents')
    op.drop_table('documents')
    
    # Drop users table (if it was created in this migration)
    # Note: In a real scenario, you might want to preserve users and just remove tenant_id
    op.drop_index('ix_users_tenant_id', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_constraint('fk_users_tenant_id_tenants', 'users', type_='foreignkey')
    op.drop_column('users', 'tenant_id')
    # Note: We're not dropping the entire users table in downgrade to preserve data
    # If you want to drop the table completely, uncomment:
    # op.drop_table('users')
    
    # Drop tenants table
    op.drop_index('ix_tenants_is_active', table_name='tenants')
    op.drop_index('ix_tenants_slug', table_name='tenants')
    op.drop_index('ix_tenants_name', table_name='tenants')
    op.drop_index('ix_tenants_id', table_name='tenants')
    op.drop_table('tenants')
