"""Operational and governance models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


class Blacklist(BaseModel):
    """Blacklist entries for users or devices."""

    __tablename__ = "blacklists"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ConfigItem(BaseModel):
    """Key-value configuration stored in DB."""

    __tablename__ = "config_items"
    __table_args__ = (UniqueConstraint("config_key", name="uq_config_key"),)

    config_key: Mapped[str] = mapped_column(String(150), nullable=False)
    config_value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
