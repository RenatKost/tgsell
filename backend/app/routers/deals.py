from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealMessage, DealStatus, Transaction, TransactionStatus, TransactionType
from app.models.user import User
from app.schemas.deal import (
    DealCreate, DealDisputeRequest, DealMessageCreate,
    DealMessageResponse, DealResponse, SellerWalletRequest,
)
from app.services.escrow import generate_escrow_wallet
from app.utils.security import get_current_user

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deals", tags=["deals"])


def _deal_to_response(deal: Deal, channel: Channel | None = None, buyer: User | None = None, seller: User | None = None, bundle=None) -> DealResponse:
    return DealResponse(
        id=deal.id,
        channel_id=deal.channel_id,
        bundle_id=deal.bundle_id,
        buyer_id=deal.buyer_id,
        seller_id=deal.seller_id,
        channel_name=channel.channel_name if channel else (bundle.name if bundle else None),
        channel_avatar_url=channel.avatar_url if channel else None,
        channel_link=channel.telegram_link if channel else None,
        bundle_name=bundle.name if bundle else None,
        bundle_channel_count=len(bundle.bundle_channels) if bundle and bundle.bundle_channels else None,
        buyer_name=buyer.first_name if buyer else None,
        seller_name=seller.first_name if seller else None,
        status=deal.status.value,
        escrow_wallet_address=deal.escrow_wallet_address,
        amount_usdt=deal.amount_usdt,
        service_fee=deal.service_fee,
        deal_group_chat_id=deal.deal_group_chat_id,
        dispute_reason=deal.dispute_reason,
        buyer_ready=deal.buyer_ready,
        seller_ready=deal.seller_ready,
        buyer_confirmed_transfer=deal.buyer_confirmed_transfer,
        seller_confirmed_transfer=deal.seller_confirmed_transfer,
        seller_payout_address=deal.seller_payout_address,
        payout_tx_hash=deal.payout_tx_hash,
        created_at=deal.created_at,
        paid_at=deal.paid_at,
        completed_at=deal.completed_at,
    )


@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    body: DealCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate a purchase — create a deal with escrow wallet.
    Accepts either channel_id (single channel) or bundle_id (network of channels).
    """
    if body.bundle_id is not None:
        # ── Bundle deal ────────────────────────────────────────────────
        from app.models.bundle import ChannelBundle, BundleStatus, BundleChannel
        from sqlalchemy.orm import selectinload as _si

        res = await db.execute(
            select(ChannelBundle)
            .options(_si(ChannelBundle.bundle_channels))
            .where(ChannelBundle.id == body.bundle_id)
        )
        bundle = res.scalar_one_or_none()
        if not bundle:
            raise HTTPException(status_code=404, detail="Bundle not found")
        if bundle.status != BundleStatus.approved:
            raise HTTPException(status_code=400, detail="Bundle is not available for purchase")
        if bundle.seller_id == user.id:
            raise HTTPException(status_code=400, detail="Cannot buy your own bundle")

        # Check no active deal for this bundle
        existing = await db.execute(
            select(Deal).where(
                Deal.bundle_id == body.bundle_id,
                Deal.status.in_([
                    DealStatus.created, DealStatus.payment_pending,
                    DealStatus.paid, DealStatus.channel_transferring,
                ]),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Bundle already has an active deal")

        wallet_address, encrypted_private_key = generate_escrow_wallet()
        fee = bundle.price * (settings.service_fee_percent / 100)

        deal = Deal(
            channel_id=None,
            bundle_id=bundle.id,
            buyer_id=user.id,
            seller_id=bundle.seller_id,
            status=DealStatus.created,
            escrow_wallet_address=wallet_address,
            escrow_private_key_encrypted=encrypted_private_key,
            amount_usdt=bundle.price,
            service_fee=fee,
        )
        db.add(deal)
        await db.commit()
        await db.refresh(deal)
        logger.info(f"[DEAL] Bundle deal #{deal.id} CREATED: buyer={user.id}, seller={bundle.seller_id}, bundle={bundle.id}, amount={bundle.price} USDT")

        seller_result = await db.execute(select(User).where(User.id == bundle.seller_id))
        seller = seller_result.scalar_one_or_none()

        payout = deal.amount_usdt - fee
        channel_count = len(bundle.bundle_channels)
        init_msg = (
            f"Угоду на сітку «{bundle.name}» створено! Каналів: {channel_count}\n"
            f"Вартість: {deal.amount_usdt} USDT\n"
            f"Комісія сервісу: 3% ({fee:.2f} USDT)\n"
            f"Продавець отримає: {payout:.2f} USDT\n\n"
            f"Підтвердіть готовність, щоб перейти до оплати."
        )
        await _add_system_message(db, deal.id, user.id, init_msg)
        await db.commit()

        try:
            from bot.main import notify_new_bundle_deal
            from aiogram import Bot
            bot = Bot(token=settings.bot_token_alerts)
            await notify_new_bundle_deal(bot, deal, bundle, user, seller)
            await bot.session.close()
        except Exception as e:
            logger.error(f"[DEAL] Failed to notify about bundle deal #{deal.id}: {e}", exc_info=True)

        return _deal_to_response(deal, None, user, seller, bundle)

    # ── Single channel deal ────────────────────────────────────────────
    if body.channel_id is None:
        raise HTTPException(status_code=422, detail="Either channel_id or bundle_id is required")

    result = await db.execute(select(Channel).where(Channel.id == body.channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status != ChannelStatus.approved:
        raise HTTPException(status_code=400, detail="Channel is not available for purchase")
    if channel.seller_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own channel")

    # Check no active deal for this channel
    existing = await db.execute(
        select(Deal).where(
            Deal.channel_id == body.channel_id,
            Deal.status.in_([
                DealStatus.created, DealStatus.payment_pending,
                DealStatus.paid, DealStatus.channel_transferring,
            ]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Channel already has an active deal")

    # Generate escrow wallet
    wallet_address, encrypted_private_key = generate_escrow_wallet()
    logger.info(f"[DEAL] Escrow wallet generated: {wallet_address} for channel #{body.channel_id}")

    # Calculate fee
    fee = channel.price * (settings.service_fee_percent / 100)

    deal = Deal(
        channel_id=channel.id,
        bundle_id=None,
        buyer_id=user.id,
        seller_id=channel.seller_id,
        status=DealStatus.created,
        escrow_wallet_address=wallet_address,
        escrow_private_key_encrypted=encrypted_private_key,
        amount_usdt=channel.price,
        service_fee=fee,
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    logger.info(f"[DEAL] Deal #{deal.id} CREATED: buyer={user.id}, seller={channel.seller_id}, channel={channel.id}, amount={channel.price} USDT, fee={fee:.2f}, escrow={wallet_address}")

    # Get seller for response
    seller_result = await db.execute(select(User).where(User.id == channel.seller_id))
    seller = seller_result.scalar_one_or_none()

    # Add initial system message with deal instructions
    fee = deal.service_fee
    payout = deal.amount_usdt - fee
    init_msg = (
        f"Угоду створено! Вартість каналу: {deal.amount_usdt} USDT\n"
        f"Комісія сервісу: 3% ({fee:.2f} USDT)\n"
        f"Продавець отримає: {payout:.2f} USDT\n\n"
        f"Підтвердіть готовність, щоб перейти до оплати."
    )
    await _add_system_message(db, deal.id, user.id, init_msg)
    await db.commit()

    # Notify via Telegram
    try:
        from bot.main import notify_new_deal
        from aiogram import Bot
        bot = Bot(token=settings.bot_token_alerts)
        logger.info(f"[DEAL] Sending Telegram notifications for deal #{deal.id}, seller.tg_id={seller.telegram_id if seller else 'no_seller'}, buyer.tg_id={user.telegram_id}")
        await notify_new_deal(bot, deal, user, seller)
        await bot.session.close()
        logger.info(f"[DEAL] Telegram notifications sent for deal #{deal.id}")
    except Exception as e:
        logger.error(f"[DEAL] Failed to notify about deal #{deal.id}: {e}", exc_info=True)

    return _deal_to_response(deal, channel, user, seller)


@router.get("/my", response_model=list[DealResponse])
async def get_my_deals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all deals where user is buyer or seller."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(or_(Deal.buyer_id == user.id, Deal.seller_id == user.id))
        .order_by(Deal.created_at.desc())
    )
    deals = result.scalars().all()
    # Load bundles for bundle deals
    from app.models.bundle import ChannelBundle, BundleChannel
    from sqlalchemy.orm import selectinload as _si
    bundle_ids = [d.bundle_id for d in deals if d.bundle_id]
    bundle_map = {}
    if bundle_ids:
        b_res = await db.execute(
            select(ChannelBundle)
            .options(_si(ChannelBundle.bundle_channels))
            .where(ChannelBundle.id.in_(bundle_ids))
        )
        bundle_map = {b.id: b for b in b_res.scalars().all()}
    return [_deal_to_response(d, d.channel, d.buyer, d.seller, bundle_map.get(d.bundle_id)) for d in deals]


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deal details (only buyer/seller/admin can see)."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id and user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Access denied")

    bundle = None
    if deal.bundle_id:
        from app.models.bundle import ChannelBundle, BundleChannel
        from sqlalchemy.orm import selectinload as _si
        b_res = await db.execute(
            select(ChannelBundle)
            .options(_si(ChannelBundle.bundle_channels))
            .where(ChannelBundle.id == deal.bundle_id)
        )
        bundle = b_res.scalar_one_or_none()

    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller, bundle)


@router.post("/{deal_id}/confirm-transfer", response_model=DealResponse)
async def confirm_transfer(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy endpoint — redirects to confirm-channel-transfer."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if deal.status != DealStatus.paid:
        raise HTTPException(status_code=400, detail="Deal is not in paid status")

    if deal.buyer_id == user.id:
        deal.buyer_confirmed_transfer = True
        await _add_system_message(db, deal.id, user.id, "Покупець підтвердив отримання каналу")
    else:
        deal.seller_confirmed_transfer = True
        await _add_system_message(db, deal.id, user.id, "Продавець підтвердив передачу каналу")

    if deal.buyer_confirmed_transfer and deal.seller_confirmed_transfer:
        deal.status = DealStatus.awaiting_payout
        deal.channel.status = ChannelStatus.sold
        payout_amount = deal.amount_usdt - deal.service_fee
        payout_msg = (
            f"Канал успішно передано!\n"
            f"Продавець, вкажіть гаманець для отримання {payout_amount:.2f} USDT."
        )
        await _add_system_message(db, deal.id, user.id, payout_msg)

    await db.commit()
    await db.refresh(deal)
    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


@router.post("/{deal_id}/dispute", response_model=DealResponse)
async def open_dispute(
    deal_id: int,
    body: DealDisputeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a dispute on a deal."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Only deal participants can dispute")
    if deal.status not in (DealStatus.paid, DealStatus.channel_transferring):
        raise HTTPException(status_code=400, detail="Cannot dispute this deal")

    deal.status = DealStatus.disputed
    deal.dispute_reason = body.reason
    logger.warning(f"[DEAL] Deal #{deal.id}: DISPUTE opened by user={user.id}, reason='{body.reason}'")
    await db.commit()
    await db.refresh(deal)

    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


# ===== Deal Flow Actions =====

async def _add_system_message(db: AsyncSession, deal_id: int, user_id: int, text: str):
    """Add a system message to deal chat."""
    msg = DealMessage(deal_id=deal_id, sender_id=user_id, text=text, is_system=True)
    db.add(msg)


@router.post("/{deal_id}/confirm-ready", response_model=DealResponse)
async def confirm_ready(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buyer or seller confirms they are ready for the deal."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if deal.status != DealStatus.created:
        raise HTTPException(status_code=400, detail="Deal is not in created status")

    if deal.buyer_id == user.id:
        deal.buyer_ready = True
        logger.info(f"[DEAL] Deal #{deal.id}: BUYER READY (user={user.id})")
        await _add_system_message(db, deal.id, user.id, f"Покупець підтвердив готовність")
    else:
        deal.seller_ready = True
        logger.info(f"[DEAL] Deal #{deal.id}: SELLER READY (user={user.id})")
        await _add_system_message(db, deal.id, user.id, f"Продавець підтвердив готовність")

    # Both ready → move to payment_pending
    if deal.buyer_ready and deal.seller_ready:
        deal.status = DealStatus.payment_pending
        logger.info(f"[DEAL] Deal #{deal.id}: STATUS → payment_pending, escrow={deal.escrow_wallet_address}, awaiting {deal.amount_usdt} USDT")
        payment_msg = (
            f"Обидві сторони готові! Очікуємо оплату {deal.amount_usdt} USDT.\n"
            f"Адреса для оплати вказана вище."
        )
        await _add_system_message(db, deal.id, user.id, payment_msg)

    await db.commit()
    await db.refresh(deal)
    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


@router.post("/{deal_id}/confirm-channel-transfer", response_model=DealResponse)
async def confirm_channel_transfer(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buyer or seller confirms channel has been transferred."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if deal.status != DealStatus.paid:
        raise HTTPException(status_code=400, detail="Deal is not in paid status")

    if deal.buyer_id == user.id:
        deal.buyer_confirmed_transfer = True
        logger.info(f"[DEAL] Deal #{deal.id}: BUYER CONFIRMED TRANSFER (user={user.id})")
        await _add_system_message(db, deal.id, user.id, f"Покупець підтвердив отримання каналу")
    else:
        deal.seller_confirmed_transfer = True
        logger.info(f"[DEAL] Deal #{deal.id}: SELLER CONFIRMED TRANSFER (user={user.id})")
        await _add_system_message(db, deal.id, user.id, f"Продавець підтвердив передачу каналу")

    # Both confirmed → awaiting payout
    if deal.buyer_confirmed_transfer and deal.seller_confirmed_transfer:
        deal.status = DealStatus.awaiting_payout
        if deal.channel:
            deal.channel.status = ChannelStatus.sold
            logger.info(f"[DEAL] Deal #{deal.id}: STATUS → awaiting_payout, channel #{deal.channel_id} SOLD, payout={deal.amount_usdt - deal.service_fee:.2f} USDT")
        elif deal.bundle_id:
            # Mark all channels in the bundle as sold
            from app.models.bundle import ChannelBundle, BundleChannel, BundleStatus
            bc_rows = (await db.execute(
                select(BundleChannel).where(BundleChannel.bundle_id == deal.bundle_id)
            )).scalars().all()
            for bc in bc_rows:
                ch_res = await db.execute(select(Channel).where(Channel.id == bc.channel_id))
                ch = ch_res.scalar_one_or_none()
                if ch:
                    ch.status = ChannelStatus.sold
            bundle_res = await db.execute(select(ChannelBundle).where(ChannelBundle.id == deal.bundle_id))
            bundle = bundle_res.scalar_one_or_none()
            if bundle:
                bundle.status = BundleStatus.sold
            logger.info(f"[DEAL] Bundle deal #{deal.id}: STATUS → awaiting_payout, bundle #{deal.bundle_id} SOLD")
        payout_amount = deal.amount_usdt - deal.service_fee
        payout_msg = (
            f"🎉 Канал успішно передано!\n\n"
            f"Продавець, вкажіть свій USDT (TRC-20) гаманець для отримання коштів:\n"
            f"💰 Вартість каналу: {deal.amount_usdt} USDT\n"
            f"📊 Комісія сервісу (3%): {deal.service_fee:.2f} USDT\n"
            f"💵 До виплати: {payout_amount:.2f} USDT"
        )
        await _add_system_message(db, deal.id, user.id, payout_msg)

    await db.commit()
    await db.refresh(deal)
    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


@router.post("/{deal_id}/seller-wallet", response_model=DealResponse)
async def set_seller_wallet(
    deal_id: int,
    body: SellerWalletRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Seller provides their USDT wallet for payout."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Only seller can provide wallet")
    if deal.status != DealStatus.awaiting_payout:
        raise HTTPException(status_code=400, detail="Deal is not awaiting payout")

    wallet = body.wallet_address.strip()
    if not wallet or len(wallet) < 20:
        raise HTTPException(status_code=400, detail="Invalid wallet address")

    deal.seller_payout_address = wallet
    logger.info(f"[PAYOUT] Deal #{deal.id}: seller wallet set to {wallet}, payout_amount={deal.amount_usdt - deal.service_fee:.2f} USDT")
    await _add_system_message(db, deal.id, user.id, f"Продавець вказав гаманець. Виконуємо переказ...")

    # Trigger payout
    payout_amount = deal.amount_usdt - deal.service_fee
    try:
        from app.services.escrow import send_trx_for_gas, transfer_usdt, sweep_trx_to_master
        import asyncio

        # Send TRX for gas fees first (7 TRX is enough for fee_limit=15)
        logger.info(f"[PAYOUT] Deal #{deal.id}: sending TRX for gas to escrow {deal.escrow_wallet_address}")
        gas_tx = send_trx_for_gas(deal.escrow_wallet_address, amount_trx=7)
        logger.info(f"[PAYOUT] Deal #{deal.id}: TRX gas tx={gas_tx or 'FAILED'}")
        if gas_tx:
            # Wait for TRX to confirm on TRON network
            await asyncio.sleep(6)

        # Try payout with retry
        tx_hash = None
        for attempt in range(2):
            logger.info(f"[PAYOUT] Deal #{deal.id}: USDT transfer attempt {attempt+1}/2 — {payout_amount:.2f} USDT → {wallet}")
            tx_hash = transfer_usdt(deal.escrow_private_key_encrypted, wallet, payout_amount)
            if tx_hash:
                logger.info(f"[PAYOUT] Deal #{deal.id}: USDT transfer SUCCESS, tx={tx_hash}")
                break
            logger.warning(f"[PAYOUT] Deal #{deal.id}: USDT transfer attempt {attempt+1} FAILED")
            if attempt == 0:
                await asyncio.sleep(10)

        if tx_hash:
            deal.payout_tx_hash = tx_hash
            deal.status = DealStatus.completed
            deal.completed_at = datetime.utcnow()
            # Record payout transaction
            payout_tx = Transaction(
                deal_id=deal.id,
                tx_hash=tx_hash,
                from_address=deal.escrow_wallet_address,
                to_address=wallet,
                amount=payout_amount,
                type=TransactionType.release,
                status=TransactionStatus.confirmed,
            )
            db.add(payout_tx)
            logger.info(f"[PAYOUT] Deal #{deal.id}: STATUS → completed, payout={payout_amount:.2f} USDT, tx={tx_hash}")
            await _add_system_message(
                db, deal.id, user.id,
                f"Виплата {payout_amount:.2f} USDT відправлена!\nTX: {tx_hash}"
            )
            # Sweep leftover TRX back to master wallet
            try:
                await asyncio.sleep(6)
                sweep_tx = sweep_trx_to_master(deal.escrow_private_key_encrypted)
                logger.info(f"[PAYOUT] Deal #{deal.id}: TRX sweep-back tx={sweep_tx or 'nothing to sweep'}")
            except Exception as sweep_err:
                logger.warning(f"[PAYOUT] Deal #{deal.id}: TRX sweep-back failed (non-critical): {sweep_err}")
        else:
            deal.status = DealStatus.disputed
            deal.dispute_reason = "Помилка автоматичної виплати"
            # Record failed transaction
            failed_tx = Transaction(
                deal_id=deal.id,
                from_address=deal.escrow_wallet_address,
                to_address=wallet,
                amount=payout_amount,
                type=TransactionType.release,
                status=TransactionStatus.failed,
            )
            db.add(failed_tx)
            logger.error(f"[PAYOUT] Deal #{deal.id}: PAYOUT FAILED after 2 attempts, STATUS → disputed")
            await _add_system_message(
                db, deal.id, user.id,
                f"Автоматична виплата не вдалася. Адміністратор вирішить це питання."
            )
    except Exception as e:
        logger.error(f"[PAYOUT] Deal #{deal.id}: EXCEPTION during payout: {e}", exc_info=True)
        deal.status = DealStatus.disputed
        deal.dispute_reason = f"Помилка виплати: {e}"
        await _add_system_message(
            db, deal.id, user.id,
            "Помилка виплати. Адміністратор розгляне це питання."
        )

    await db.commit()
    await db.refresh(deal)
    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


@router.post("/{deal_id}/call-admin", response_model=DealMessageResponse)
async def call_admin(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Call admin to the deal chat. Sends Telegram notification."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel))
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Add system message
    msg = DealMessage(
        deal_id=deal_id,
        sender_id=user.id,
        text=f"{user.first_name} викликав адміністратора. Очікуйте відповіді.",
        is_system=True,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # Notify admin group via Telegram
    try:
        from bot.main import notify_admin_called
        from aiogram import Bot
        bot = Bot(token=settings.bot_token_alerts)
        channel_name = deal.channel.channel_name if deal.channel else f"#{deal.channel_id}"
        await notify_admin_called(bot, deal.id, channel_name, user.first_name)
        await bot.session.close()
    except Exception as e:
        logger.error(f"Failed to notify admin group for deal #{deal.id}: {e}")

    return DealMessageResponse(
        id=msg.id,
        deal_id=msg.deal_id,
        sender_id=msg.sender_id,
        sender_name=user.first_name,
        text=msg.text,
        is_system=True,
        created_at=msg.created_at,
    )


# ===== Deal Messages (Chat) =====

@router.get("/{deal_id}/messages", response_model=list[DealMessageResponse])
async def get_deal_messages(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages for a deal."""
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id and user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(DealMessage)
        .where(DealMessage.deal_id == deal_id)
        .order_by(DealMessage.created_at.asc())
    )
    messages = result.scalars().all()

    # Load sender names
    sender_ids = {m.sender_id for m in messages}
    senders = {}
    if sender_ids:
        res = await db.execute(select(User).where(User.id.in_(sender_ids)))
        senders = {u.id: u for u in res.scalars().all()}

    return [
        DealMessageResponse(
            id=m.id,
            deal_id=m.deal_id,
            sender_id=m.sender_id,
            sender_name=senders.get(m.sender_id, None) and senders[m.sender_id].first_name,
            text=m.text,
            is_system=m.is_system,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/{deal_id}/messages", response_model=DealMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_deal_message(
    deal_id: int,
    body: DealMessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message in deal chat."""
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id and user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Access denied")

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Message too long")

    message = DealMessage(
        deal_id=deal_id,
        sender_id=user.id,
        text=text,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    return DealMessageResponse(
        id=message.id,
        deal_id=message.deal_id,
        sender_id=message.sender_id,
        sender_name=user.first_name,
        text=message.text,
        is_system=False,
        created_at=message.created_at,
    )
