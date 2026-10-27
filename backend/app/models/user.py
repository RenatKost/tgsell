import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user)
    usdt_wallet: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Moderation block (migration 0027). is_active stays the hard deactivation switch.
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Alerts-bot dialog (migration 0033): /start seen; last "chat not found"/blocked on send.
    tg_bot_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tg_bot_unreachable_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    blocked_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # «Приведи продавця» (migration 0055): own referral code; who referred this user (first bind wins)
    ref_code: Mapped[str | None] = mapped_column(String(16), unique=True, index=True, nullable=True)
    referred_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    channels = relationship("Channel", back_populates="seller", foreign_keys="Channel.seller_id")
    deals_as_buyer = relationship("Deal", back_populates="buyer", foreign_keys="Deal.buyer_id")
    deals_as_seller = relationship("Deal", back_populates="seller", foreign_keys="Deal.seller_id")

    @property
    def alert_bot_started(self) -> bool:
        """True when the user pressed Start in @tgsell_alert_bot and is still reachable (no DB column)."""
        return bool(self.telegram_id and self.tg_bot_started_at and not self.tg_bot_unreachable_at)


class AdminAuditLog(Base):
    """Append-only log of admin actions (migration 0027)."""

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
