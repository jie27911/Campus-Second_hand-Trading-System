"""补充模型：购物车、搜索、会话等。"""
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from apps.core.models.base import Base, TimestampMixin


# ==================== 购物车模型 ====================

class CartItem(Base, TimestampMixin):
    """购物车表"""
    __tablename__ = "cart_items"
    
    id = Column(BigInteger, primary_key=True, autoincrement=False)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    item_id = Column(BigInteger, nullable=False, comment="商品ID")
    quantity = Column(Integer, nullable=False, default=1, comment="数量")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'item_id', name='unique_user_item'),
        Index('idx_user_id', 'user_id'),
        Index('idx_item_id', 'item_id'),
        Index('idx_created', 'created_at'),
    )


# ==================== 搜索模型 ====================

class SearchHistory(Base):
    """搜索历史表"""
    __tablename__ = "search_history"
    
    id = Column(BigInteger, primary_key=True, autoincrement=False)
    user_id = Column(BigInteger, comment="用户ID")
    keyword = Column(String(200), nullable=False, comment="搜索关键词")
    result_count = Column(Integer, default=0, comment="搜索结果数量")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_user_id', 'user_id'),
        Index('idx_keyword', 'keyword'),
        Index('idx_created', 'created_at'),
    )


# ==================== 消息模型 ====================

class Message(Base, TimestampMixin):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(BigInteger, primary_key=True, autoincrement=False)
    sender_id = Column(BigInteger, nullable=False, comment="发送者ID")
    receiver_id = Column(BigInteger, nullable=False, comment="接收者ID")
    item_id = Column(BigInteger, comment="关联商品ID")
    content = Column(Text, nullable=False, comment="消息内容")
    is_read = Column(Boolean, default=False, comment="是否已读")
    is_deleted_by_sender = Column(Boolean, default=False, comment="发送者是否删除")
    is_deleted_by_receiver = Column(Boolean, default=False, comment="接收者是否删除")
    read_at = Column(DateTime, comment="阅读时间")
    sync_version = Column(Integer, default=0)
    v_clock = Column(Text, comment="向量时钟(JSON文本)")
    
    __table_args__ = (
        Index('idx_sender_id', 'sender_id'),
        Index('idx_receiver_id', 'receiver_id'),
        Index('idx_item_id', 'item_id'),
        Index('idx_created', 'created_at'),
    )


# ==================== 会话模型 ====================

class Conversation(Base, TimestampMixin):
    """会话表（消息聊天）"""
    __tablename__ = "conversations"
    
    id = Column(BigInteger, primary_key=True, autoincrement=False)
    user1_id = Column(BigInteger, nullable=False, comment="用户1 ID")
    user2_id = Column(BigInteger, nullable=False, comment="用户2 ID")
    item_id = Column(BigInteger, comment="关联商品ID（可选）")
    
    # 最后消息信息
    last_message_id = Column(BigInteger, comment="最后一条消息ID")
    last_message_content = Column(Text, comment="最后消息内容")
    last_message_at = Column(DateTime, comment="最后消息时间")
    
    # 未读计数
    user1_unread_count = Column(Integer, default=0, comment="用户1未读消息数")
    user2_unread_count = Column(Integer, default=0, comment="用户2未读消息数")
    
    # 删除标记
    user1_deleted = Column(Boolean, default=False, comment="用户1是否删除")
    user2_deleted = Column(Boolean, default=False, comment="用户2是否删除")
    
    __table_args__ = (
        UniqueConstraint('user1_id', 'user2_id', name='unique_conversation'),
        Index('idx_user1', 'user1_id'),
        Index('idx_user2', 'user2_id'),
        Index('idx_item', 'item_id'),
        Index('idx_updated', 'updated_at'),
    )


# ==================== 系统设置模型 ====================

class SystemSetting(Base, TimestampMixin):
    """系统运行时配置（管理员可在后台调整）"""

    __tablename__ = "system_settings"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    category = Column(String(64), nullable=False, comment="设置分类")
    key = Column(String(128), nullable=False, comment="设置键")
    value = Column(JSON, nullable=False, default=dict, comment="配置内容(JSON)")
    updated_by = Column(BigInteger, ForeignKey("users.id"), comment="最后修改人")

    __table_args__ = (
        UniqueConstraint('category', 'key', name='uq_system_settings_category_key'),
        Index('ix_system_settings_category', 'category'),
    )


# ==================== 通知模型 ====================

class Notification(Base, TimestampMixin):
    """系统通知表（用于冲突/交易/消息等提醒）"""

    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, comment="用户ID")
    type = Column(String(50), nullable=False, comment="通知类型")
    title = Column(String(200), nullable=False, comment="通知标题")
    content = Column(Text, comment="通知内容")
    related_id = Column(BigInteger, comment="关联对象ID")
    related_type = Column(String(50), comment="关联对象类型")
    is_read = Column(Boolean, default=False, comment="是否已读")
    sync_version = Column(Integer, default=0)

    __table_args__ = (
        Index('idx_user_id', 'user_id'),
        Index('idx_type', 'type'),
        Index('idx_is_read', 'is_read'),
        Index('idx_created', 'created_at'),
    )
