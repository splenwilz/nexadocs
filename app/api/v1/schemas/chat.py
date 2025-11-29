"""
Chat API schemas
Defines request/response models for chat endpoints
"""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """Request to send a message in a conversation"""
    message: str = Field(..., min_length=1, max_length=5000, description="User's question or message")
    conversation_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional conversation ID. If not provided, a new conversation will be created."
    )


class Citation(BaseModel):
    """Citation reference to a document"""
    document_id: str = Field(..., description="UUID of the document")
    document_name: str = Field(..., description="Name of the document")
    page_number: int = Field(..., description="Page number in the document")


class ChatMessageResponse(BaseModel):
    """Response containing AI assistant's answer"""
    answer: str = Field(..., description="AI assistant's answer")
    citations: List[Citation] = Field(default_factory=list, description="List of document citations")
    chunks_used: int = Field(..., description="Number of document chunks used to generate the answer")
    conversation_id: uuid.UUID = Field(..., description="Conversation ID (new or existing)")
    message_id: uuid.UUID = Field(..., description="Message ID")


class ConversationResponse(BaseModel):
    """Conversation metadata"""
    id: uuid.UUID = Field(..., description="Conversation ID")
    tenant_id: uuid.UUID = Field(..., description="Tenant ID")
    user_id: str = Field(..., description="User ID (WorkOS format)")
    title: Optional[str] = Field(None, description="Conversation title")
    created_at: datetime = Field(..., description="When conversation was created")
    updated_at: datetime = Field(..., description="When conversation was last updated")
    message_count: int = Field(..., description="Number of messages in conversation")


class MessageResponse(BaseModel):
    """Message in a conversation"""
    id: uuid.UUID = Field(..., description="Message ID")
    conversation_id: uuid.UUID = Field(..., description="Conversation ID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    citations: Optional[str] = Field(None, description="JSON string of citations (for assistant messages)")
    created_at: datetime = Field(..., description="When message was created")


class ConversationListResponse(BaseModel):
    """List of conversations"""
    conversations: List[ConversationResponse] = Field(..., description="List of conversations")
    total: int = Field(..., description="Total number of conversations")


class ConversationDetailResponse(BaseModel):
    """Detailed conversation with messages"""
    conversation: ConversationResponse = Field(..., description="Conversation metadata")
    messages: List[MessageResponse] = Field(..., description="Messages in the conversation")

