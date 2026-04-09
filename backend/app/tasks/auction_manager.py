"""Background task: manage auction lifecycle (activate scheduled, end expired)."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.enums import ParseMode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.auction import Auction, AuctionBid
from app.models.channel import Channel
from app.models.deal import Deal, DealMessage, DealStatus
from app.models.user import User
from app.services.escrow import generate_escrow_wallet

logger = logging.getLogger(__name__)


async def _create_deal_for_auction(db: AsyncSession, auction: Auction) -> Deal | None:
    """Create a deal + escrow wallet for a finished auction with a winner."""
    wallet_address, encrypted_private_key = generate_escrow_wallet()

    fee = round(auction.current_price * (settings.service_fee_percent / 100), 2)

    deal = Deal(
        channel_id=auction.channel_id,
        buyer_id=auction.winner_id,
        seller_id=auction.seller_id,
        status=DealStatus.created,
        escrow_wallet_address=wallet_address,
        escrow_private_key_encrypted=encrypted_private_key,
        amount_usdt=auction.current_price,
        service_fee=fee,
    )
    db.add(deal)
    await db.flush()  # Get deal.id

    # Mark channel as sold
    channel = await db.get(Channel, auction.channel_id)
    channel_name = channel.channel_name if channel else "—"
    if channel:
        channel.status = "sold"

    # Add initial system message
    payout = deal.amount_usdt - fee
    init_msg = (
        f"Угоду створено за результатами аукціону!\n"
        f"Вартість каналу: {deal.amount_usdt} USDT\n"
        f"Комісія сервісу: {settings.service_fee_percent}% ({fee:.2f} USDT)\n"
        f"Продавець отримає: {payout:.2f} USDT\n\n"
        f"Підтвердіть готовність, щоб перейти до оплати."
    )
    db.add(DealMessage(
        deal_id=deal.id,
        sender_id=auction.seller_id,
        text=init_msg,
        is_system=True,
    ))

    logger.info(
        f"Deal #{deal.id} created for auction #{auction.id}: "
        f"winner={auction.winner_id}, price={auction.current_price}, escrow={wallet_address}"
    )
    return deal, channel_name


async def _notify_auction_ended(deal: Deal, auction: Auction, channel_name: str, winner: User, seller: User):
    """Send Telegram notifications about auction end + deal creation."""
    bot = Bot(token=settings.bot_token_alerts)
    frontend_url = settings.frontend_url.rstrip("/")

    try:
        # Notify winner (buyer)
        if winner.telegram_id:
            buyer_text = (
                f"🎉 <b>Вітаємо! Ви виграли аукціон!</b>\n\n"
                f"📺 Канал: {channel_name}\n"
                f"💰 Ваша ставка: {auction.current_price} USDT\n\n"
                f"Угода #{deal.id} створена. Підтвердіть готовність та оплатіть:\n"
                f"💳 <code>{deal.escrow_wallet_address}</code>\n"
                f"Мережа: TRON (TRC-20 USDT)\n\n"
                f"<a href='{frontend_url}/deal/{deal.id}'>Перейти до угоди →</a>"
            )
            try:
                await bot.send_message(winner.telegram_id, buyer_text, parse_mode=ParseMode.HTML)
                logger.info(f"[AUCTION] Winner {winner.telegram_id} notified about auction #{auction.id}")
            except Exception as e:
                logger.error(f"[AUCTION] Failed to notify winner {winner.telegram_id}: {e}")

        # Notify seller
        if seller.telegram_id:
            seller_text = (
                f"🏆 <b>Аукціон завершено — канал продано!</b>\n\n"
                f"📺 Канал: {channel_name}\n"
                f"💰 Фінальна ціна: {auction.current_price} USDT\n"
                f"👤 Переможець: {winner.first_name}\n\n"
                f"Угода #{deal.id} створена. Очікуємо оплату від покупця.\n\n"
                f"<a href='{frontend_url}/deal/{deal.id}'>Перейти до угоди →</a>"
            )
            try:
                await bot.send_message(seller.telegram_id, seller_text, parse_mode=ParseMode.HTML)
                logger.info(f"[AUCTION] Seller {seller.telegram_id} notified about auction #{auction.id}")
            except Exception as e:
                logger.error(f"[AUCTION] Failed to notify seller {seller.telegram_id}: {e}")

        # Notify admin group
        if settings.admin_group_id:
            admin_text = (
                f"🏆 <b>Аукціон #{auction.id} завершено</b>\n\n"
                f"📺 {channel_name}\n"
                f"💰 Ціна: {auction.current_price} USDT\n"
                f"👤 Переможець: {winner.first_name} (id={winner.id})\n"
                f"📦 Угода #{deal.id} створена"
            )
            try:
                await bot.send_message(settings.admin_group_id, admin_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"[AUCTION] Failed to notify admin group: {e}")

    finally:
        await bot.session.close()


async def _notify_auction_no_bids(auction: Auction, channel_name: str, seller: User):
    """Notify seller that auction ended with no bids."""
    if not seller.telegram_id:
        return

    bot = Bot(token=settings.bot_token_alerts)
    try:
        text = (
            f"⏰ <b>Аукціон завершено — ставок не було</b>\n\n"
            f"📺 Канал: {channel_name}\n"
            f"Ви можете створити новий аукціон або виставити канал на пряму продаж."
        )
        await bot.send_message(seller.telegram_id, text, parse_mode=ParseMode.HTML)
        logger.info(f"[AUCTION] Seller {seller.telegram_id} notified: no bids on auction #{auction.id}")
    except Exception as e:
        logger.error(f"[AUCTION] Failed to notify seller about no-bid auction: {e}")
    finally:
        await bot.session.close()


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
        await _finalize_auction(db, auction)

    # 3. Handle buyout auctions that were ended by place_bid but not yet finalized
    result = await db.execute(
        select(Auction).where(
            Auction.status == "ended",
            Auction.winner_id.isnot(None),
        )
    )
    for auction in result.scalars().all():
        # Check if deal already exists for this auction's channel+winner
        existing_deal = (await db.execute(
            select(Deal).where(
                Deal.channel_id == auction.channel_id,
                Deal.buyer_id == auction.winner_id,
                Deal.seller_id == auction.seller_id,
            )
        )).scalar_one_or_none()
        if not existing_deal:
            logger.info(f"Auction #{auction.id} was buyout — creating deal now")
            await _finalize_auction(db, auction)

    await db.commit()


async def _finalize_auction(db: AsyncSession, auction: Auction):
    """Create deal and send notifications for a finished auction."""
    channel = await db.get(Channel, auction.channel_id)
    channel_name = channel.channel_name if channel else "—"

    if auction.winner_id:
        try:
            deal, channel_name = await _create_deal_for_auction(db, auction)

            winner = await db.get(User, auction.winner_id)
            seller = await db.get(User, auction.seller_id)

            if winner and seller:
                await _notify_auction_ended(deal, auction, channel_name, winner, seller)

        except Exception as e:
            logger.error(f"Failed to create deal for auction #{auction.id}: {e}", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
    else:
        logger.info(f"Auction #{auction.id} ended with no bids")
        seller = await db.get(User, auction.seller_id)
        # Restore channel to approved so seller can relist
        if channel and channel.status == "approved":
            pass  # Already in correct state
        if seller:
            await _notify_auction_no_bids(auction, channel_name, seller)


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
