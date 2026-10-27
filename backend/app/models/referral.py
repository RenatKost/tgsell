"""«Приведи продавця» reward ledger (migration 0055). One row per referred seller (UNIQUE)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (UniqueConstraint("referred_user_id", name="uq_referral_rewards_referred_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    referred_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    source_channel_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    awarded_channel_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # "applied" (free 7-day Top given) | "credit" (waits for referrer's next lot) | "revoked"
    created_at: Mapped[datetime] = mapped_column(DateTime)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
