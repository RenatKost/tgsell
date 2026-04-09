"""Background task: manage auction lifecycle (activate scheduled, end expired)."""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.auction import Auction, AuctionBid
from app.models.channel import Channel
from app.models.deal import Deal
from app.models.user import User

logger = logging.getLogger(__name__)


async def _process_auctions(db: AsyncSession):
    now = datetime.utcnow()

    # 1. Activate scheduled auctions whose start time has passed
    result = await db.execute(
        select(Auction).where(Auction.status == "scheduled", Auction.starts_at <= now)
    )
    for auction in result.scalars().all():
        auction.status = "active"
        logger.info(f"Auction #{auction.id} activated (channel #{auction.channel_id})")

    # 2. End auctions past their end time
    result = await db.execute(
        select(Auction).where(Auction.status == "active", Auction.ends_at <= now)
    )
    for auction in result.scalars().all():
        auction.status = "ended"
        logger.info(f"Auction #{auction.id} ended (channel #{auction.channel_id})")

        if auction.winner_id:
            # Create a Deal for the winner
            try:
                from app.services.escrow import create_escrow_wallet
                wallet = await create_escrow_wallet()

                deal = Deal(
                    channel_id=auction.channel_id,
                    buyer_id=auction.winner_id,
                    seller_id=auction.seller_id,
                    status="payment_pending",
                    escrow_wallet_address=wallet["address"],
                    escrow_private_key_encrypted=wallet["private_key_encrypted"],
                    amount_usdt=auction.current_price,
                    service_fee=round(auction.current_price * 0.05, 2),
                )
                db.add(deal)

                # Mark channel
                channel = await db.get(Channel, auction.channel_id)
                if channel:
                    channel.status = "sold"

                logger.info(
                    f"Deal created for auction #{auction.id}: "
                    f"winner={auction.winner_id}, price={auction.current_price}"
                )

                # Notify via bot
                try:
                    from bot.main import alert_bot, notify_new_deal
                    winner = await db.get(User, auction.winner_id)
                    seller = await db.get(User, auction.seller_id)
                    if winner and seller and alert_bot:
                        await notify_new_deal(alert_bot, deal, winner, seller)
                except Exception as e:
                    logger.warning(f"Auction #{auction.id} deal notification failed: {e}")

            except Exception as e:
                logger.error(f"Failed to create deal for auction #{auction.id}: {e}", exc_info=True)
        else:
            logger.info(f"Auction #{auction.id} ended with no bids")

    await db.commit()


async def run_auction_manager(interval_seconds: int = 60):
    """Run auction manager every N seconds."""
    logger.info(f"Auction manager started (interval={interval_seconds}s)")
    await asyncio.sleep(10)  # small initial delay
    while True:
        try:
            async with async_session() as db:
                await _process_auctions(db)
        except Exception as e:
            logger.error(f"Auction manager error: {e}", exc_info=True)
            from app.services.alerts import alert_service_down
            await alert_service_down("Auction Manager", str(e))
        await asyncio.sleep(interval_seconds)
