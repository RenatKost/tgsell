"""Background task: Monitor USDT deposits for active deals."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.deal import Deal, DealMessage, DealStatus, Transaction, TransactionStatus, TransactionType
from app.services.escrow import get_usdt_balance
from bot.main import notify_payment_received

logger = logging.getLogger(__name__)


async def check_payments_once():
    """Check all pending deals for incoming USDT payments."""
    async with async_session() as db:
        # Get deals awaiting payment
        result = await db.execute(
            select(Deal).where(
                Deal.status == DealStatus.payment_pending
            )
        )
        deals = result.scalars().all()

        for deal in deals:
            try:
                # Check timeout
                if deal.created_at:
                    deadline = deal.created_at + timedelta(hours=settings.payment_timeout_hours)
                    if datetime.now(timezone.utc) > deadline.replace(tzinfo=timezone.utc):
                        deal.status = DealStatus.cancelled
                        logger.info(f"Deal #{deal.id} cancelled: payment timeout")
                        await db.commit()
                        continue

                # Check USDT balance on escrow wallet
                balance = get_usdt_balance(deal.escrow_wallet_address)

                if balance >= deal.amount_usdt:
                    deal.status = DealStatus.paid
                    deal.paid_at = datetime.utcnow()

                    # Record transaction
                    tx = Transaction(
                        deal_id=deal.id,
                        to_address=deal.escrow_wallet_address,
                        amount=balance,
                        type=TransactionType.deposit,
                        status=TransactionStatus.confirmed,
                    )
                    db.add(tx)
                    await db.commit()

                    logger.info(
                        f"Deal #{deal.id} PAID: {balance} USDT received at {deal.escrow_wallet_address}"
                    )

                    # Add system message to deal chat
                    sys_msg = DealMessage(
                        deal_id=deal.id,
                        sender_id=deal.buyer_id,
                        text=(
                            f"💰 Оплата {balance} USDT отримана!\n\n"
                            f"Продавець, передайте канал покупцю:\n"
                            f"Telegram → Settings → Channel → Administrators → Transfer Ownership\n\n"
                            f"Покупець, після отримання каналу натисніть 'Підтвердити отримання'"
                        ),
                        is_system=True,
                    )
                    db.add(sys_msg)
                    await db.commit()

                    # Notify via Telegram
                    try:
                        from app.models.user import User
                        buyer = await db.get(User, deal.buyer_id)
                        seller = await db.get(User, deal.seller_id)
                        if buyer and seller:
                            bot = Bot(token=settings.bot_token_alerts)
                            await notify_payment_received(bot, deal, buyer, seller)
                    except Exception as e:
                        logger.error(f"Failed to send payment notification for deal #{deal.id}: {e}")

                elif balance > 0:
                    # Partial payment
                    if deal.status != DealStatus.payment_pending:
                        deal.status = DealStatus.payment_pending
                        await db.commit()
                    logger.info(
                        f"Deal #{deal.id}: partial payment {balance}/{deal.amount_usdt} USDT"
                    )

            except Exception as e:
                logger.error(f"Error checking payment for deal #{deal.id}: {e}")


async def run_payment_checker(interval_seconds: int = 30):
    """Run payment checker loop."""
    logger.info(f"Payment checker started (interval: {interval_seconds}s)")
    while True:
        try:
            await check_payments_once()
        except Exception as e:
            logger.error(f"Payment checker error: {e}")
        await asyncio.sleep(interval_seconds)
