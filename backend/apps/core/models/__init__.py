"""Aggregate models for CampuSwap."""
from .additional import (
    CartItem,
    Conversation,
    Message,
    Notification,
    SearchHistory,
    SystemSetting,
)
from .ai import AIAction, AIChat, AIInsight, AIModel, FraudPattern
from .base import Base, BaseModel, PrimaryKeyMixin, SyncVersionMixin, TimestampMixin
from .inventory import (
    Campus,
    Category,
    Favorite,
    Follow,
    Item,
    ItemAttachment,
    ItemMedia,
    ItemTag,
    Tag,
)
from .operations import Blacklist, ConfigItem
from .sync import ConflictRecord, DailyStat, SyncConfig, SyncLog, SyncWorkerState
from .transactions import Delivery, Offer, Payment, Review, Transaction, TransactionLog
from .users import Permission, Role, RolePermission, User, UserPreference, UserProfile, UserRole

__all__ = [
    "AIAction",
    "AIChat",
    "AIInsight",
    "AIModel",
    "Base",
    "BaseModel",
    "Blacklist",
    "Campus",
    "CartItem",
    "Category",
    "ConfigItem",
    "ConflictRecord",
    "Conversation",
    "DailyStat",
    "Delivery",
    "Favorite",
    "Follow",
    "FraudPattern",
    "Item",
    "ItemAttachment",
    "ItemMedia",
    "ItemTag",
    "Message",
    "Notification",
    "Offer",
    "Payment",
    "Permission",
    "Review",
    "Role",
    "RolePermission",
    "SearchHistory",
    "SystemSetting",
    "SyncConfig",
    "SyncLog",
    "SyncWorkerState",
    "Tag",
    "Transaction",
    "TransactionLog",
    "User",
    "UserPreference",
    "UserProfile",
    "UserRole",
]
