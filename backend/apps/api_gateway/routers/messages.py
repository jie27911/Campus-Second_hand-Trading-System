"""
消息/聊天路由模块
处理用户间的消息发送、接收、会话管理等功能
"""
from datetime import datetime
import logging
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api_gateway.dependencies import get_current_user, get_db_session
from apps.core.models import Item, User
from apps.services.business_logic import MessageService

router = APIRouter(prefix="/messages", tags=["消息管理"])

logger = logging.getLogger(__name__)


# ==================== Pydantic Models ====================

class MessageSendRequest(BaseModel):
    """发送消息请求"""
    receiver_id: Union[int, str] = Field(..., description="接收者ID")
    content: str = Field(..., min_length=1, max_length=5000, description="消息内容")
    message_type: str = Field(default="text", description="消息类型: text/image/file")
    item_id: Optional[Union[int, str]] = Field(None, description="关联商品ID")


class MessageResponse(BaseModel):
    """消息响应"""
    # Snowflake BIGINT ids may exceed JS safe integer; return as strings.
    id: str
    conversation_id: str
    sender_id: str
    sender_name: str
    sender_avatar: Optional[str] = None
    receiver_id: str
    receiver_name: str
    receiver_avatar: Optional[str] = None
    content: str
    message_type: str
    item_id: Optional[str] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    """会话响应"""
    id: str
    other_user_id: str
    other_user_name: str
    other_user_avatar: Optional[str] = None
    last_message: Optional[str] = None
    last_message_time: Optional[datetime] = None
    unread_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """消息列表响应"""
    messages: List[MessageResponse]
    total: int
    page: int
    page_size: int


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    conversations: List[ConversationResponse]
    total: int
    total_unread: int


class ConversationStartRequest(BaseModel):
    """开启会话请求"""
    user_id: Optional[Union[int, str]] = Field(None, description="想要联系的用户ID")
    username: Optional[str] = Field(None, description="想要联系的用户名(更安全，避免前端大整数精度丢失)")
    item_id: Optional[Union[int, str]] = Field(None, description="关联的商品ID")


# ==================== API路由 ====================

@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageSendRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    发送消息
    
    可以关联商品ID，方便买卖双方沟通
    """
    try:
        receiver_id = int(payload.receiver_id)
        item_id = int(payload.item_id) if payload.item_id is not None else None
        result = MessageService.send_message(
            session=session,
            sender_id=current_user.id,
            receiver_id=receiver_id,
            content=payload.content,
            item_id=item_id
        )
        session.commit()
        return MessageResponse(**result)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="receiver_id/item_id 必须是可解析的整数")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"发送失败: {str(e)}")


@router.get("/conversations", response_model=ConversationListResponse)
async def get_conversations(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    获取会话列表
    
    按最后消息时间排序
    """
    try:
        result = MessageService.get_conversations(session, current_user.id)
        return ConversationListResponse(
            conversations=[ConversationResponse(**conv) for conv in result["conversations"]],
            total=result["total"],
            total_unread=result["total_unread"]
        )
    except Exception as e:
        logger.exception("Failed to get conversations for user_id=%s", current_user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取会话列表失败: {str(e)}")


@router.post("/conversations/start", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def start_conversation(
    payload: ConversationStartRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """首次联系时创建或获取会话"""
    # Resolve target user by priority:
    # 1) item_id -> item's seller_id (hub DB authoritative)
    # 2) username -> hub user id (safe for JS; avoids Snowflake precision loss)
    # 3) user_id -> legacy path
    target_user_id: Optional[int] = None

    if payload.item_id is not None:
        item_id = int(payload.item_id)
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
        target_user_id = int(item.seller_id)
    elif payload.username:
        target = session.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        target_user_id = int(target.id)
    elif payload.user_id is not None:
        target_user_id = int(payload.user_id)
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="必须提供 user_id 或 username 或 item_id")

    if int(target_user_id) == int(current_user.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法与自己创建会话")
    try:
        conv = MessageService.get_or_create_conversation(
            session=session,
            user1_id=current_user.id,
            user2_id=target_user_id,
            item_id=payload.item_id
        )
        session.commit()
        conv_data = MessageService.serialize_conversation(session, conv, current_user.id)
        return ConversationResponse(**conv_data)
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建会话失败: {str(e)}")


@router.get("/conversations/{conversation_id}", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):

    """
    获取会话消息列表
    
    按时间倒序返回，支持分页加载历史消息
    """
    try:
        result = MessageService.get_conversation_messages(
            session=session,
            user_id=current_user.id,
            conversation_id=conversation_id,
            page=page,
            page_size=page_size
        )
        session.commit()  # 提交已读标记
        return MessageListResponse(
            messages=[MessageResponse(**msg) for msg in result["messages"]],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"]
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取消息失败: {str(e)}")


@router.put("/{message_id}/read")
async def mark_message_read(
    message_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    标记消息为已读
    """
    try:
        result = MessageService.mark_message_read(session, current_user.id, message_id)
        session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"操作失败: {str(e)}")


@router.put("/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    标记会话所有消息为已读
    """
    try:
        result = MessageService.mark_conversation_read(session, current_user.id, conversation_id)
        session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"操作失败: {str(e)}")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    删除会话
    
    注意：只是隐藏会话，不会删除消息记录
    """
    try:
        result = MessageService.delete_conversation(session, current_user.id, conversation_id)
        session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除失败: {str(e)}")


@router.get("/unread/count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    获取未读消息总数
    
    用于顶部导航栏的徽章显示
    """
    try:
        return MessageService.get_unread_count(session, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取失败: {str(e)}")


@router.get("/search")
async def search_messages(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    搜索消息
    
    支持按内容、联系人名称搜索
    """
    try:
        return MessageService.search_messages(
            session=session,
            user_id=current_user.id,
            keyword=keyword,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"搜索失败: {str(e)}")
