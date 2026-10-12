"""Master wallet resource snapshots (migration 0028)."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MasterWalletSnapshot(Base):
    __tablename__ = "master_wallet_snapshots"
    __table_args__ = (Index("ix_master_wallet_snapshots_at", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    trx_sun: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # NULL = unknown
    energy_available: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bandwidth_available: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
