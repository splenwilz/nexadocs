"""
Chat API routes for conversation and messaging
Handles tenant-scoped chat operations with RAG-powered responses
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ConversationResponse,
    ConversationListResponse,
    ConversationDetailResponse,
    MessageResponse,
    Citation,
)
from app.core.database import get_db
from app.core.tenant import CurrentTenant
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.api.v1.schemas.auth import WorkOSUserResponse
from app.services.chat import ChatService
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    summary="Send a message",
    description="Send a message to the AI assistant and get a response based on tenant's documents",
    status_code=status.HTTP_200_OK,
)
async def send_message(
    request: ChatMessageRequest,
    tenant: CurrentTenant = ...,
    current_user: WorkOSUserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    """
    Send a message to the AI assistant.
    
    This endpoint:
    1. Creates or uses existing conversation
    2. Stores user message
    3. Generates AI response using RAG (searches tenant's documents)
    4. Stores assistant message with citations
    5. Returns the response
    
    The AI response is generated using:
    - Semantic search in tenant's document embeddings
    - LLM generation with retrieved context
    - Citations to source documents and pages
    
    Args:
        request: Chat message request with question and optional conversation_id
        tenant: Current tenant (from dependency injection)
        current_user: Current authenticated user (from dependency injection)
        db: Database session (from dependency injection)
    
    Returns:
        ChatMessageResponse with answer, citations, and message IDs
    
    Raises:
        HTTPException: 400 if request is invalid
        HTTPException: 500 if processing fails
    """
    chat_service = ChatService()
    
    try:
        conversation, user_message, assistant_message = await chat_service.send_message(
            db=db,
            tenant_id=tenant.id,
            user_id=current_user.id,
            message_text=request.message,
            conversation_id=request.conversation_id,
        )
        
        # Parse citations from JSON
        citations = []
        if assistant_message.citations:
            try:
                citations_data = json.loads(assistant_message.citations)
                citations = [
                    Citation(
                        document_id=cit["document_id"],
                        document_name=cit["document_name"],
                        page_number=cit["page_number"],
                    )
                    for cit in citations_data
                ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse citations: {e}")
        
        # Count chunks used (approximate from citations)
        chunks_used = len(citations)  # Rough estimate
        
        await db.commit()
        
        return ChatMessageResponse(
            answer=assistant_message.content,
            citations=citations,
            chunks_used=chunks_used,
            conversation_id=conversation.id,
            message_id=assistant_message.id,
        )
    
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error sending message: {e}", exc_info=True)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Full traceback: {error_traceback}")
        # Return detailed error for debugging
        error_detail = f"Error: {str(e)}\n\nTraceback:\n{error_traceback}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        ) from e


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List conversations",
    description="Get a list of conversations for the current user",
    status_code=status.HTTP_200_OK,
)
async def list_conversations(
    skip: int = Query(0, ge=0, description="Number of conversations to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of conversations to return"),
    tenant: CurrentTenant = ...,
    current_user: WorkOSUserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    """
    Get a list of conversations for the current user.
    
    Results are automatically filtered by tenant_id and user_id for security.
    
    Args:
        skip: Number of conversations to skip (pagination)
        limit: Maximum number of conversations to return (pagination)
        tenant: Current tenant (from dependency injection)
        current_user: Current authenticated user (from dependency injection)
        db: Database session (from dependency injection)
    
    Returns:
        ConversationListResponse with list of conversations
    """
    chat_service = ChatService()
    
    conversations = await chat_service.get_conversations(
        db=db,
        tenant_id=tenant.id,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    
    # Convert to response format
    conversation_responses = [
        ConversationResponse(
            id=conv.id,
            tenant_id=conv.tenant_id,
            user_id=conv.user_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=len(conv.messages) if hasattr(conv, 'messages') else 0,
        )
        for conv in conversations
    ]
    
    return ConversationListResponse(
        conversations=conversation_responses,
        total=len(conversation_responses),
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation",
    description="Get a conversation with all its messages",
    status_code=status.HTTP_200_OK,
)
async def get_conversation(
    conversation_id: uuid.UUID,
    tenant: CurrentTenant = ...,
    current_user: WorkOSUserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """
    Get a conversation with all its messages.
    
    Args:
        conversation_id: UUID of the conversation
        tenant: Current tenant (from dependency injection)
        current_user: Current authenticated user (from dependency injection)
        db: Database session (from dependency injection)
    
    Returns:
        ConversationDetailResponse with conversation and messages
    
    Raises:
        HTTPException: 404 if conversation not found
    """
    chat_service = ChatService()
    
    conversation = await chat_service.get_conversation(
        db=db,
        conversation_id=conversation_id,
        tenant_id=tenant.id,
        user_id=current_user.id,
    )
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    messages = await chat_service.get_messages(
        db=db,
        conversation_id=conversation_id,
        tenant_id=tenant.id,
    )
    
    return ConversationDetailResponse(
        conversation=ConversationResponse(
            id=conversation.id,
            tenant_id=conversation.tenant_id,
            user_id=conversation.user_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(messages),
        ),
        messages=[
            MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                citations=msg.citations,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
    )


@router.delete(
    "/conversations/{conversation_id}",
    summary="Delete conversation",
    description="Delete a conversation and all its messages",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    tenant: CurrentTenant = ...,
    current_user: WorkOSUserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a conversation and all its messages.
    
    Args:
        conversation_id: UUID of the conversation
        tenant: Current tenant (from dependency injection)
        current_user: Current authenticated user (from dependency injection)
        db: Database session (from dependency injection)
    
    Returns:
        None (204 No Content)
    
    Raises:
        HTTPException: 404 if conversation not found
    """
    chat_service = ChatService()
    
    deleted = await chat_service.delete_conversation(
        db=db,
        conversation_id=conversation_id,
        tenant_id=tenant.id,
        user_id=current_user.id,
    )
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    await db.commit()
    return None

