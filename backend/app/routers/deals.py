from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.channel import Channel, ChannelStatus
from app.models.deal import Deal, DealMessage, DealStatus
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


def _deal_to_response(deal: Deal, channel: Channel | None = None, buyer: User | None = None, seller: User | None = None) -> DealResponse:
    return DealResponse(
        id=deal.id,
        channel_id=deal.channel_id,
        buyer_id=deal.buyer_id,
        seller_id=deal.seller_id,
        channel_name=channel.channel_name if channel else None,
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
    """Initiate a purchase — create a deal with escrow wallet."""
    # Get channel
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

    # Calculate fee
    fee = channel.price * (settings.service_fee_percent / 100)

    deal = Deal(
        channel_id=channel.id,
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

    # Get seller for response
    seller_result = await db.execute(select(User).where(User.id == channel.seller_id))
    seller = seller_result.scalar_one_or_none()

    # Add initial system message with deal instructions
    fee = deal.service_fee
    payout = deal.amount_usdt - fee
    init_msg = (
        f"📋 Угода #{deal.id} створена!\n\n"
        f"Цикл угоди:\n"
        f"1️⃣ Обидві сторони підтверджують готовність\n"
        f"2️⃣ Покупець оплачує {deal.amount_usdt} USDT на ескроу-гаманець\n"
        f"3️⃣ Продавець передає канал покупцю\n"
        f"4️⃣ Обидві сторони підтверджують передачу\n"
        f"5️⃣ Продавець отримує кошти\n\n"
        f"💰 Вартість: {deal.amount_usdt} USDT\n"
        f"📊 Комісія сервісу: 3% ({fee:.2f} USDT)\n"
        f"💵 Продавець отримає: {payout:.2f} USDT"
    )
    await _add_system_message(db, deal.id, user.id, init_msg)
    await db.commit()

    # Notify via Telegram
    try:
        from bot.main import notify_new_deal
        from aiogram import Bot
        bot = Bot(token=settings.bot_token_alerts)
        await notify_new_deal(bot, deal, user, seller)
        await bot.session.close()
    except Exception as e:
        logger.error(f"Failed to notify about deal #{deal.id}: {e}")

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
    return [_deal_to_response(d, d.channel, d.buyer, d.seller) for d in deals]


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

    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


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
        await _add_system_message(db, deal.id, user.id, "✅ Покупець підтвердив отримання каналу")
    else:
        deal.seller_confirmed_transfer = True
        await _add_system_message(db, deal.id, user.id, "✅ Продавець підтвердив передачу каналу")

    if deal.buyer_confirmed_transfer and deal.seller_confirmed_transfer:
        deal.status = DealStatus.awaiting_payout
        deal.channel.status = ChannelStatus.sold
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
        await _add_system_message(db, deal.id, user.id, f"✅ Покупець {user.first_name} підтвердив готовність до угоди")
    else:
        deal.seller_ready = True
        await _add_system_message(db, deal.id, user.id, f"✅ Продавець {user.first_name} підтвердив готовність до угоди")

    # Both ready → move to payment_pending
    if deal.buyer_ready and deal.seller_ready:
        deal.status = DealStatus.payment_pending
        payment_msg = (
            f"💰 Обидві сторони готові!\n\n"
            f"Покупець, переведіть {deal.amount_usdt} USDT (TRC-20) на адресу:\n"
            f"{deal.escrow_wallet_address}\n\n"
            f"⚠️ Переводьте тільки USDT через мережу TRC-20!\n"
            f"📊 Комісія сервісу (3%) буде утримана при виплаті продавцю\n"
            f"⏱ Оплата перевіряється автоматично кожні 30 секунд"
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
        await _add_system_message(db, deal.id, user.id, f"✅ Покупець підтвердив отримання каналу")
    else:
        deal.seller_confirmed_transfer = True
        await _add_system_message(db, deal.id, user.id, f"✅ Продавець підтвердив передачу каналу")

    # Both confirmed → awaiting payout
    if deal.buyer_confirmed_transfer and deal.seller_confirmed_transfer:
        deal.status = DealStatus.awaiting_payout
        deal.channel.status = ChannelStatus.sold
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
    await _add_system_message(db, deal.id, user.id, f"💳 Продавець вказав гаманець для виплати")

    # Trigger payout
    payout_amount = deal.amount_usdt - deal.service_fee
    try:
        from app.services.escrow import send_trx_for_gas, transfer_usdt
        import asyncio

        # Send TRX for gas fees first
        gas_tx = send_trx_for_gas(deal.escrow_wallet_address)
        if gas_tx:
            # Wait for TRX to confirm on TRON network
            await asyncio.sleep(15)

        # Try payout with retry
        tx_hash = None
        for attempt in range(2):
            tx_hash = transfer_usdt(deal.escrow_private_key_encrypted, wallet, payout_amount)
            if tx_hash:
                break
            if attempt == 0:
                logger.warning(f"Payout attempt 1 failed for deal #{deal.id}, retrying in 10s...")
                await asyncio.sleep(10)

        if tx_hash:
            deal.payout_tx_hash = tx_hash
            deal.status = DealStatus.completed
            deal.completed_at = datetime.utcnow()
            await _add_system_message(
                db, deal.id, user.id,
                f"✅ Виплата {payout_amount:.2f} USDT відправлена! TX: {tx_hash}"
            )
        else:
            deal.status = DealStatus.disputed
            deal.dispute_reason = "Помилка автоматичної виплати"
            await _add_system_message(
                db, deal.id, user.id,
                f"⚠️ Автоматична виплата не вдалася. Адміністратор вирішить це протягом 24 годин."
            )
    except Exception as e:
        logger.error(f"Payout failed for deal #{deal.id}: {e}")
        deal.status = DealStatus.disputed
        deal.dispute_reason = f"Помилка виплати: {e}"
        await _add_system_message(
            db, deal.id, user.id,
            "⚠️ Помилка виплати. Адміністратор розгляне це питання протягом 24 годин."
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
        text=f"🛡️ {user.first_name} викликав адміністратора в чат\n📩 Повідомлення відправлено адміністраторам. Очікуйте відповіді.",
        is_system=True,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # Notify admins via Telegram
    try:
        from bot.main import notify_admin_called
        admin_result = await db.execute(
            select(User).where(User.role.in_(["admin", "moderator"]))
        )
        admins = admin_result.scalars().all()
        from aiogram import Bot
        bot = Bot(token=settings.bot_token_alerts)
        channel_name = deal.channel.channel_name if deal.channel else f"#{deal.channel_id}"
        for admin in admins:
            if admin.telegram_id:
                try:
                    await notify_admin_called(bot, admin.telegram_id, deal.id, channel_name, user.first_name)
                except Exception:
                    pass
        await bot.session.close()
    except Exception as e:
        logger.error(f"Failed to notify admins for deal #{deal.id}: {e}")

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
