"""
Chat service for managing conversations and messages
Handles conversation creation, message storage, and RAG queries
"""
import logging
import time
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.rag import RAGService

logger = logging.getLogger(__name__)


class ChatService:
    """
    Service for managing chat conversations and messages
    
    Handles:
    - Creating conversations
    - Storing messages
    - Generating AI responses using RAG
    - Retrieving conversation history
    """
    
    def __init__(self):
        """Initialize chat service"""
        self.rag_service = RAGService()
    
    async def send_message(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: str,
        message_text: str,
        conversation_id: Optional[uuid.UUID] = None,
    ) -> tuple[Conversation, Message, Message]:
        """
        Send a message and get AI response
        
        Creates or uses existing conversation, stores user message,
        generates AI response using RAG, and stores assistant message.
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant
            user_id: WorkOS user ID (string)
            message_text: User's message/question
            conversation_id: Optional existing conversation ID
            
        Returns:
            Tuple of (conversation, user_message, assistant_message)
            
        Raises:
            Exception: If message processing fails
        """
        try:
            total_start = time.time()
            
            # Get or create conversation
            conv_start = time.time()
            if conversation_id:
                result = await db.execute(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.tenant_id == tenant_id,  # Security: verify tenant
                        Conversation.user_id == user_id,  # Security: verify user
                    )
                )
                conversation = result.scalar_one_or_none()
                
                if not conversation:
                    raise ValueError(f"Conversation {conversation_id} not found or access denied")
            else:
                # Create new conversation
                conversation = Conversation(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    title=None,  # Will be set from first message
                )
                db.add(conversation)
                await db.flush()
            
            # Set conversation title from first message if not set
            if not conversation.title:
                # Use first 50 characters of first message as title
                conversation.title = message_text[:50] + ("..." if len(message_text) > 50 else "")
                await db.flush()
            conv_time = time.time() - conv_start
            print(f"[PERF] Chat: Conversation setup: {conv_time:.3f}s")
            
            # Create user message
            user_msg_start = time.time()
            user_message = Message(
                conversation_id=conversation.id,
                role="user",
                content=message_text,
                citations=None,
            )
            db.add(user_message)
            await db.flush()
            user_msg_time = time.time() - user_msg_start
            print(f"[PERF] Chat: User message save: {user_msg_time:.3f}s")
            
            # Generate AI response using RAG
            rag_start = time.time()
            logger.info(f"Generating RAG response for conversation {conversation.id}")
            rag_result = await self.rag_service.query(
                tenant_id=tenant_id,  # Pass UUID directly
                question=message_text,
            )
            rag_time = time.time() - rag_start
            print(f"[PERF] Chat: RAG query: {rag_time:.3f}s")
            
            # Format citations as JSON
            citations_json = json.dumps(rag_result["citations"]) if rag_result["citations"] else None
            
            # Create assistant message
            assistant_msg_start = time.time()
            assistant_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=rag_result["answer"],
                citations=citations_json,
            )
            db.add(assistant_message)
            
            # Update conversation timestamp
            conversation.updated_at = datetime.now(timezone.utc)
            
            await db.flush()
            assistant_msg_time = time.time() - assistant_msg_start
            print(f"[PERF] Chat: Assistant message save: {assistant_msg_time:.3f}s")
            
            total_time = time.time() - total_start
            print(f"[PERF] Chat: Total send_message: {total_time:.3f}s (conv: {conv_time:.3f}s, user_msg: {user_msg_time:.3f}s, rag: {rag_time:.3f}s, assistant_msg: {assistant_msg_time:.3f}s)")
            logger.info(
                f"[PERF] Created messages in conversation {conversation.id}: "
                f"user message {user_message.id}, assistant message {assistant_message.id} - Total: {total_time:.3f}s"
            )
            
            return conversation, user_message, assistant_message
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            raise
    
    async def get_conversations(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Conversation]:
        """
        Get list of conversations for a user
        
        Args:
            db: Database session
            tenant_id: UUID of the tenant
            user_id: WorkOS user ID (string)
            skip: Number of conversations to skip
            limit: Maximum number of conversations to return
            
        Returns:
            List of Conversation objects
        """
        query = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
        ).order_by(Conversation.updated_at.desc())
        
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: str,
    ) -> Optional[Conversation]:
        """
        Get a conversation with messages
        
        Args:
            db: Database session
            conversation_id: UUID of the conversation
            tenant_id: UUID of the tenant (for security)
            user_id: WorkOS user ID (for security)
            
        Returns:
            Conversation if found and accessible, None otherwise
        """
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
    
    async def get_messages(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> List[Message]:
        """
        Get all messages in a conversation
        
        Args:
            db: Database session
            conversation_id: UUID of the conversation
            tenant_id: UUID of the tenant (for security)
            
        Returns:
            List of Message objects ordered by creation time
        """
        # Verify conversation belongs to tenant
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            return []
        
        # Get messages
        result = await db.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
            ).order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())
    
    async def delete_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: str,
    ) -> bool:
        """
        Delete a conversation and all its messages
        
        Args:
            db: Database session
            conversation_id: UUID of the conversation
            tenant_id: UUID of the tenant (for security)
            user_id: WorkOS user ID (for security)
            
        Returns:
            True if conversation was deleted, False if not found
        """
        conversation = await self.get_conversation(db, conversation_id, tenant_id, user_id)
        
        if not conversation:
            return False
        
        # Delete conversation (messages will be cascade deleted)
        await db.delete(conversation)
        await db.flush()
        
        logger.info(f"Deleted conversation {conversation_id}")
        return True

