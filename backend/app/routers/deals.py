from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.money_display import money2_str
from app.config import settings
from app.database import get_db
from app.models.channel import Channel, ChannelStatus
from app.models.deal import ACTIVE_DEAL_STATUSES, Deal, DealMessage, DealStatus, Transaction, TransactionStatus, TransactionType
from app.models.user import User
from app.schemas.deal import (
    ChecklistItemResponse, ChecklistSideResponse, ChecklistToggleRequest,
    DealChecklistResponse, DealCreate, DealDisputeRequest, DealMessageCreate,
    DealMessageResponse, DealResponse, OverpayRefundAddressRequest, SellerWalletRequest,
)
from app.services import deal_checklist as checklist_svc
from app.services.escrow import generate_escrow_wallet
from app.services.payment_deadlines import created_stage_deadline, payment_stage_deadline
from app.utils.timeutil import utcnow_naive
from app.services.deal_lifecycle import (
    claim_deal_for_transfer,
    has_payout_tx,
    mark_deal_completed,
    PayoutClaimError,
    release_payout_claim,
)
from app.utils.security import get_current_user, get_current_user_or_blocked
from app.services import moderation
from app.utils.avatars import public_channel_avatar_url

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
        channel_avatar_url=public_channel_avatar_url(channel.id, channel.avatar_url) if channel else None,
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
        received_usdt=deal.received_usdt,
        overpay_units=deal.overpay_units,
        overpay_refund_address=deal.overpay_refund_address,
        overpay_status=deal.overpay_status,
        created_at=deal.created_at,
        paid_at=deal.paid_at,
        completed_at=deal.completed_at,
        balance_stars=deal.balance_stars,
        balance_ton=deal.balance_ton,
    )


async def _ensure_seller_not_blocked(db: AsyncSession, seller_id: int) -> None:
    seller = await db.get(User, seller_id)
    if seller is not None and seller.is_blocked:
        raise HTTPException(status_code=400, detail="Продавець недоступний — нові угоди заборонені")


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

        # Row lock serializes concurrent purchases of the same bundle.
        res = await db.execute(
            select(ChannelBundle)
            .options(_si(ChannelBundle.bundle_channels).selectinload(BundleChannel.channel))
            .where(ChannelBundle.id == body.bundle_id)
            .with_for_update(of=ChannelBundle)
        )
        bundle = res.scalar_one_or_none()
        if not bundle:
            raise HTTPException(status_code=404, detail="Bundle not found")
        if bundle.status != BundleStatus.approved:
            raise HTTPException(status_code=400, detail="Bundle is not available for purchase")
        if bundle.seller_id == user.id:
            raise HTTPException(status_code=400, detail="Cannot buy your own bundle")
        await _ensure_seller_not_blocked(db, bundle.seller_id)

        # Check no active deal for this bundle
        existing = await db.execute(
            select(Deal.id).where(
                Deal.bundle_id == body.bundle_id,
                Deal.status.in_(ACTIVE_DEAL_STATUSES),
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Bundle already has an active deal")

        # Every channel of the bundle must be purchasable and not reserved by
        # its own single-channel deal. Lock channel rows to block a racing
        # single-channel purchase.
        ch_ids = [bc.channel_id for bc in bundle.bundle_channels]
        if ch_ids:
            await db.execute(
                select(Channel.id).where(Channel.id.in_(ch_ids)).order_by(Channel.id).with_for_update()
            )
            for bc in bundle.bundle_channels:
                if bc.channel is None or bc.channel.status != ChannelStatus.approved:
                    raise HTTPException(status_code=400, detail="Bundle is not available for purchase")
            busy = await db.execute(
                select(Deal.id).where(
                    Deal.channel_id.in_(ch_ids),
                    Deal.status.in_(ACTIVE_DEAL_STATUSES),
                ).limit(1)
            )
            if busy.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="A channel of this bundle already has an active deal")

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
            # Task 31: snapshot of seller-stated balance (sum over bundle channels)
            **checklist_svc.bundle_balance_snapshot([bc.channel for bc in bundle.bundle_channels]),
            # 'created' stage timeout (auto-cancel only if escrow balance is confirmed 0)
            payment_deadline_at=created_stage_deadline(utcnow_naive()),
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
            f"Вартість: {money2_str(deal.amount_usdt)} USDT\n"
            f"Комісія сервісу: {settings.service_fee_percent:g}% ({money2_str(fee)} USDT)\n"
            f"Продавець отримає: {money2_str(payout)} USDT\n\n"
            f"Підтвердіть готовність, щоб перейти до оплати."
        )
        await _add_system_message(db, deal.id, user.id, init_msg, event="deal_created")
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

    # Row lock serializes concurrent purchases of the same channel.
    result = await db.execute(select(Channel).where(Channel.id == body.channel_id).with_for_update())
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.status != ChannelStatus.approved:
        raise HTTPException(status_code=400, detail="Channel is not available for purchase")
    if channel.seller_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own channel")
    await _ensure_seller_not_blocked(db, channel.seller_id)

    # Check no active deal for this channel
    existing = await db.execute(
        select(Deal.id).where(
            Deal.channel_id == body.channel_id,
            Deal.status.in_(ACTIVE_DEAL_STATUSES),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Channel already has an active deal")

    # Channel reserved through a bundle that has an active deal.
    from app.models.bundle import BundleChannel as _BC
    bundle_busy = await db.execute(
        select(Deal.id)
        .join(_BC, _BC.bundle_id == Deal.bundle_id)
        .where(_BC.channel_id == body.channel_id, Deal.status.in_(ACTIVE_DEAL_STATUSES))
        .limit(1)
    )
    if bundle_busy.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Channel is part of a bundle with an active deal")

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
        # Task 31: snapshot of seller-stated balance (later lot edits don't change it)
        **checklist_svc.balance_snapshot(channel),
        # 'created' stage timeout (auto-cancel only if escrow balance is confirmed 0)
        payment_deadline_at=created_stage_deadline(utcnow_naive()),
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
        f"Угоду створено! Вартість каналу: {money2_str(deal.amount_usdt)} USDT\n"
        f"Комісія сервісу: {settings.service_fee_percent:g}% ({money2_str(fee)} USDT)\n"
        f"Продавець отримає: {money2_str(payout)} USDT\n\n"
        f"Підтвердіть готовність, щоб перейти до оплати."
    )
    await _add_system_message(db, deal.id, user.id, init_msg, event="deal_created")
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
    user: User = Depends(get_current_user_or_blocked),
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
    user: User = Depends(get_current_user_or_blocked),
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
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Legacy endpoint — same logic as confirm-channel-transfer (checklist-gated)."""
    return await _confirm_transfer_impl(deal_id, user, db)


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
    await _add_system_message(db, deal.id, user.id, "Відкрито спір. Гарант розгляне угоду.", event="dispute_opened")
    logger.warning(f"[DEAL] Deal #{deal.id}: DISPUTE opened by user={user.id}, reason='{body.reason}'")
    await db.commit()
    await db.refresh(deal)

    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


# ===== Deal Flow Actions =====

async def _add_system_message(db: AsyncSession, deal_id: int, user_id: int, text: str, event: str = "deal_step"):
    """Add a system message to deal chat (chat v2 helper; actor kept in meta)."""
    import app.services.chat as chat_svc

    chat_svc.system(db, deal_id, event, text, actor_id=user_id)


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
        await _add_system_message(db, deal.id, user.id, "Покупець підтвердив готовність", event="ready_confirmed")
    else:
        deal.seller_ready = True
        logger.info(f"[DEAL] Deal #{deal.id}: SELLER READY (user={user.id})")
        await _add_system_message(db, deal.id, user.id, "Продавець підтвердив готовність", event="ready_confirmed")

    # Both ready → move to payment_pending
    if deal.buyer_ready and deal.seller_ready:
        deal.status = DealStatus.payment_pending
        # Payment window starts now (PAYMENT_TIMEOUT_HOURS); checker cancels only after
        # a confirmed zero balance past this deadline.
        deal.payment_deadline_at = payment_stage_deadline(utcnow_naive())
        logger.info(f"[DEAL] Deal #{deal.id}: STATUS → payment_pending, escrow={deal.escrow_wallet_address}, awaiting {deal.amount_usdt} USDT")
        payment_msg = (
            f"Обидві сторони готові! Очікуємо оплату {deal.amount_usdt} USDT.\n"
            f"Адреса для оплати вказана вище."
        )
        await _add_system_message(db, deal.id, user.id, payment_msg, event="payment_requested")

    await db.commit()
    await db.refresh(deal)
    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


@router.post("/{deal_id}/confirm-channel-transfer", response_model=DealResponse)
async def confirm_channel_transfer(
    deal_id: int,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Buyer or seller confirms channel has been transferred (checklist-gated)."""
    return await _confirm_transfer_impl(deal_id, user, db)


async def _confirm_transfer_impl(deal_id: int, user: User, db: AsyncSession) -> DealResponse:
    """Confirm transfer for the caller's side.

    Rejects (400) while the caller's required checklist items are open.
    → awaiting_payout ONLY when both sides confirmed AND all required items
    of both sides are done (checklist_svc.can_advance_to_awaiting_payout).
    """
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
        .with_for_update(of=Deal)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if checklist_svc.side_for_user(deal, user.id) is None:
        raise HTTPException(status_code=403, detail="Access denied")
    moderation.ensure_deal_action_allowed(user, deal)
    if deal.status not in checklist_svc.TRANSFER_STATUSES:
        raise HTTPException(status_code=400, detail="Угода не в статусі передачі каналу")

    now = datetime.utcnow()
    items = await checklist_svc.ensure_checklist(db, deal, now)
    try:
        side = checklist_svc.check_confirm_allowed(deal, user.id, items)
    except checklist_svc.ChecklistError as e:
        await db.commit()  # keep lazily-created checklist rows; releases row lock
        raise HTTPException(status_code=e.http_status, detail=e.message)

    if side == checklist_svc.SIDE_BUYER:
        deal.buyer_confirmed_transfer = True
        logger.info(f"[DEAL] Deal #{deal.id}: BUYER CONFIRMED TRANSFER (user={user.id})")
        await _add_system_message(db, deal.id, user.id, "Покупець підтвердив отримання каналу", event="transfer_confirmed")
    else:
        deal.seller_confirmed_transfer = True
        logger.info(f"[DEAL] Deal #{deal.id}: SELLER CONFIRMED TRANSFER (user={user.id})")
        await _add_system_message(db, deal.id, user.id, "Продавець підтвердив передачу каналу", event="transfer_confirmed")
    checklist_svc.mark_transferring(deal)
    checklist_svc.record_checklist_activity(deal, now)

    if checklist_svc.can_advance_to_awaiting_payout(deal, items):
        await checklist_svc.advance_to_awaiting_payout(db, deal)
        await _add_system_message(db, deal.id, user.id, checklist_svc.payout_request_message(deal), event="awaiting_payout")

    await db.commit()
    await db.refresh(deal)
    return _deal_to_response(deal, deal.channel, deal.buyer, deal.seller)


# ===== Transfer checklist =====

def _checklist_response(
    deal: Deal,
    items: list,
    user: User,
    *,
    auto_verify_message: str | None = None,
) -> DealChecklistResponse:
    from app.services.channel_stats import get_telethon_health

    by_key = {i.key: i for i in items}
    my_side = checklist_svc.side_for_user(deal, user.id)
    active = deal.status in checklist_svc.TRANSFER_STATUSES

    def _side(side: str) -> ChecklistSideResponse:
        out = []
        for d in checklist_svc.defs_for_side(side, deal, items):
            row = by_key.get(d.key)
            out.append(ChecklistItemResponse(
                key=d.key, side=d.side, label=d.label, hint=d.hint,
                required=d.required,
                done=bool(row and row.done),
                done_by=row.done_by if row else None,
                done_at=row.done_at if row else None,
                auto_verified=row.auto_verified if row else None,
                auto_note=row.auto_note if row else None,
                auto_checked_at=row.auto_checked_at if row else None,
            ))
        req = [i for i in out if i.required]
        return ChecklistSideResponse(
            side=side,
            label=checklist_svc.SIDE_LABELS[side],
            items=out,
            required_total=len(req),
            required_done=sum(1 for i in req if i.done),
            confirmed=checklist_svc.side_confirmed(deal, side),
        )

    try:
        telethon_ok = bool(get_telethon_health().get("ok"))
    except Exception:
        telethon_ok = False

    return DealChecklistResponse(
        deal_id=deal.id,
        status=deal.status.value,
        active=active,
        my_side=my_side,
        can_edit=active and my_side is not None,
        seller=_side(checklist_svc.SIDE_SELLER),
        buyer=_side(checklist_svc.SIDE_BUYER),
        all_required_done=checklist_svc.all_required_done(items, deal),
        balance_stars=deal.balance_stars,
        balance_ton=deal.balance_ton,
        last_activity_at=deal.last_checklist_activity_at,
        telethon_available=telethon_ok,
        auto_verify_message=auto_verify_message,
    )


def _can_view_checklist(deal: Deal, user: User) -> bool:
    return (
        deal.buyer_id == user.id
        or deal.seller_id == user.id
        or user.role in ("admin", "moderator")
    )


@router.get("/{deal_id}/checklist", response_model=DealChecklistResponse)
async def get_deal_checklist(
    deal_id: int,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Transfer checklist (buyer, seller, admin/moderator). Lazily created for paid deals."""
    deal = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if not _can_view_checklist(deal, user):
        raise HTTPException(status_code=403, detail="Access denied")

    if deal.status in checklist_svc.TRANSFER_STATUSES:
        items = await checklist_svc.ensure_checklist(db, deal)
        await db.commit()
        await db.refresh(deal)
    else:
        items = await checklist_svc.load_items(db, deal.id)
    return _checklist_response(deal, items, user)


# NOTE: declared before /checklist/{key} so "auto-verify" is not captured as a key.
@router.post("/{deal_id}/checklist/auto-verify", response_model=DealChecklistResponse)
async def auto_verify_deal_checklist(
    deal_id: int,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Best-effort Telethon check (owner / admins / subscribers).

    Stores auto_verified + auto_note only. Never ticks items, never changes
    deal status, never moves money. Degrades gracefully when Telethon is down.
    """
    from app.services.checklist_autoverify import run_auto_verify

    deal = (
        await db.execute(
            select(Deal)
            .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
            .where(Deal.id == deal_id)
        )
    ).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if not _can_view_checklist(deal, user):
        raise HTTPException(status_code=403, detail="Access denied")
    moderation.ensure_deal_action_allowed(user, deal)
    if deal.status not in checklist_svc.TRANSFER_STATUSES:
        raise HTTPException(status_code=400, detail="Автоперевірка доступна лише під час передачі каналу")

    items = await checklist_svc.ensure_checklist(db, deal)
    message = await run_auto_verify(db, deal, items)
    if message and message.startswith("Автоперевірку виконано"):
        import app.services.chat as chat_svc

        chat_svc.system(db, deal, "auto_verify",
                        "🔎 Автоперевірку виконано — результати біля пунктів чекліста "
                        "(лише підказка, не замінює ручну перевірку).", actor_id=user.id)
    await db.commit()
    await db.refresh(deal)
    items = await checklist_svc.load_items(db, deal.id)
    return _checklist_response(deal, items, user, auto_verify_message=message)


# Task 31. NOTE: declared before /checklist/{key} so "balance-mismatch" is not captured as a key.
@router.post("/{deal_id}/checklist/balance-mismatch", response_model=DealResponse)
async def report_balance_mismatch(
    deal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buyer: «баланс не відповідає» → opens a dispute via the existing dispute flow."""
    deal = (await db.execute(
        select(Deal)
        .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
        .where(Deal.id == deal_id)
    )).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id:
        raise HTTPException(status_code=403, detail="Повідомити про невідповідність балансу може лише покупець")
    if not checklist_svc.deal_has_balance(deal):
        raise HTTPException(status_code=400, detail="Для цієї угоди баланс не вказано")
    stated = checklist_svc.format_balance(deal.balance_stars, deal.balance_ton)
    reason = f"Баланс не відповідає заявленому продавцем ({stated})"
    return await open_dispute(deal_id, DealDisputeRequest(reason=reason), user, db)


@router.post("/{deal_id}/checklist/{key}", response_model=DealChecklistResponse)
async def toggle_deal_checklist_item(
    deal_id: int,
    key: str,
    body: ChecklistToggleRequest | None = Body(default=None),
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Tick/untick a checklist item. Only the owning side may change its items."""
    if key not in checklist_svc.ITEMS_BY_KEY:
        raise HTTPException(status_code=404, detail="Невідомий пункт чек-листа")

    deal = (
        await db.execute(
            select(Deal)
            .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
            .where(Deal.id == deal_id)
            .with_for_update(of=Deal)
        )
    ).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    moderation.ensure_deal_action_allowed(user, deal)
    try:
        _item_def, side = checklist_svc.check_toggle_allowed(deal, user.id, key)
    except checklist_svc.ChecklistError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)

    now = datetime.utcnow()
    items = await checklist_svc.ensure_checklist(db, deal, now)
    row = next((i for i in items if i.key == key), None)
    if row is None:  # should not happen after ensure
        raise HTTPException(status_code=500, detail="Checklist item missing")

    new_done = (not row.done) if body is None or body.done is None else bool(body.done)
    try:
        checklist_svc.check_untick_allowed(deal, side, bool(row.done), new_done)
    except checklist_svc.ChecklistError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)

    if new_done != bool(row.done):
        was_side_complete = not checklist_svc.open_required_defs(items, side, deal)
        row.done = new_done
        row.done_by = user.id if new_done else None
        row.done_at = now if new_done else None
        checklist_svc.mark_transferring(deal)
        checklist_svc.record_checklist_activity(deal, now)
        logger.info(
            f"[CHECKLIST] deal #{deal.id} {side} {'✓' if new_done else '✗'} {key} (user={user.id})"
        )
        await _add_system_message(
            db, deal.id, user.id,
            f"{checklist_svc.SIDE_LABELS[side]} {'відмітив' if new_done else 'зняв позначку'}: {_item_def.label}",
            event="checklist_item",
        )
        if not was_side_complete and not checklist_svc.open_required_defs(items, side, deal):
            label = checklist_svc.SIDE_LABELS[side]
            await _add_system_message(
                db, deal.id, user.id,
                f"{label} виконав усі обов’язкові пункти чек-листа передачі ✅",
                event="checklist_side_done",
            )

        # Legacy/edge: both already confirmed earlier → last tick completes the gate.
        if checklist_svc.can_advance_to_awaiting_payout(deal, items):
            await checklist_svc.advance_to_awaiting_payout(db, deal)
            await _add_system_message(db, deal.id, user.id, checklist_svc.payout_request_message(deal), event="awaiting_payout")

    await db.commit()
    await db.refresh(deal)
    items = await checklist_svc.load_items(db, deal.id)
    return _checklist_response(deal, items, user)


@router.post("/{deal_id}/seller-wallet", response_model=DealResponse)
async def set_seller_wallet(
    deal_id: int,
    body: SellerWalletRequest,
    response: Response,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Seller provides their USDT wallet for payout.

    Money-safety: claim the deal row (FOR UPDATE → payout_in_progress + commit)
    BEFORE any on-chain broadcast so a parallel request cannot double-pay.
    """
    from app.services import payouts

    # 1) Lock deal row — second concurrent request waits here.
    result = await db.execute(
        select(Deal).where(Deal.id == deal_id).with_for_update()
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Only seller can provide wallet")
    moderation.ensure_deal_action_allowed(user, deal)

    async def _respond():
        result = await db.execute(
            select(Deal)
            .options(selectinload(Deal.channel), selectinload(Deal.buyer), selectinload(Deal.seller))
            .where(Deal.id == deal_id)
            .execution_options(populate_existing=True)
        )
        d = result.scalar_one()
        return _deal_to_response(d, d.channel, d.buyer, d.seller)

    # 2) Idempotency: already paid — do not send again.
    if has_payout_tx(deal):
        await db.commit()  # release lock
        return await _respond()

    # Real base58check address; never master or any escrow.
    try:
        wallet = await payouts.validate_destination(db, body.wallet_address)
    except payouts.PayoutError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)

    current_status = deal.status
    if current_status != DealStatus.awaiting_payout:
        await db.rollback()
        if current_status == DealStatus.payout_in_progress:
            raise HTTPException(status_code=409, detail="Виплата вже обробляється")
        raise HTTPException(status_code=400, detail="Deal is not awaiting_payout")

    units = payouts.release_units(deal)
    payout_amount = payouts.units_to_usdt(units)

    # 3) Master TRX must cover gas BEFORE claim (insufficient/unknown → no claim, 503).
    try:
        await payouts.precheck_gas(deal, wallet, units)
    except payouts.PayoutError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)

    # 4) Atomic claim + job row in ONE commit (no unresolved outgoing tx allowed).
    try:
        await payouts.claim_for_payout(db, deal, expected_status=DealStatus.awaiting_payout)
    except PayoutClaimError as e:
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.message)

    deal.seller_payout_address = wallet
    payouts.enqueue_transfer(
        db, deal, tx_type=TransactionType.release, to_address=wallet, amount_units=units,
        restore_status=DealStatus.awaiting_payout,
    )
    await _add_system_message(
        db, deal.id, user.id,
        f"Продавець вказав гаманець. Виплату {payout_amount} USDT поставлено в чергу — "
        "статус оновиться після підтвердження мережею.",
    )
    await db.commit()
    logger.info(
        f"[PAYOUT] Deal #{deal.id}: CLAIMED + queued release {payout_amount} USDT → {wallet}"
    )
    response.status_code = 202
    return await _respond()


@router.post("/{deal_id}/overpay-refund-address")
async def set_overpay_refund_address(
    deal_id: int,
    body: OverpayRefundAddressRequest,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Buyer enters the TRON address for the overpayment refund (never the sender address).

    The refund is queued only after the seller payout succeeded (or right away if it already did).
    """
    from app.services import payouts
    from app.services.payouts import PayoutError

    deal = (await db.execute(select(Deal).where(Deal.id == deal_id).with_for_update())).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id:
        raise HTTPException(status_code=403, detail="Тільки покупець вказує адресу повернення")
    moderation.ensure_deal_action_allowed(user, deal)
    if not deal.overpay_units or deal.overpay_status != "awaiting_address":
        raise HTTPException(status_code=400, detail="Для цієї угоди немає переплати, що очікує повернення")
    try:
        wallet = await payouts.validate_destination(db, body.wallet_address)
    except PayoutError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    deal.overpay_refund_address = wallet
    await _add_system_message(
        db, deal.id, user.id,
        f"Покупець вказав адресу для повернення переплати {payouts.units_to_usdt(deal.overpay_units)} USDT: {wallet}",
        event="overpay_address",
    )
    payouts.maybe_enqueue_overpay_refund(db, deal)
    await db.commit()
    return {"overpay_status": deal.overpay_status, "overpay_refund_address": wallet}


@router.get("/{deal_id}/payout-status")
async def get_payout_status(
    deal_id: int,
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Poll payout progress (buyer/seller of the deal)."""
    from app.services import payouts

    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if user.id not in (deal.buyer_id, deal.seller_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await payouts.payout_status(db, deal)


@router.post("/{deal_id}/call-admin", response_model=DealMessageResponse)
async def call_admin(
    deal_id: int,
    user: User = Depends(get_current_user_or_blocked),
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
    moderation.ensure_deal_action_allowed(user, deal)

    # Add system message
    import app.services.chat as chat_svc

    msg = chat_svc.system(db, deal_id, "admin_called",
                          f"{user.first_name} викликав адміністратора. Очікуйте відповіді.", actor_id=user.id)
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
    user: User = Depends(get_current_user_or_blocked),
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
    user: User = Depends(get_current_user_or_blocked),
    db: AsyncSession = Depends(get_db),
):
    """Send a message in deal chat."""
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.buyer_id != user.id and deal.seller_id != user.id and user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Access denied")
    moderation.ensure_deal_action_allowed(user, deal)

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Message too long")

    message = DealMessage(
        deal_id=deal_id,
        sender_id=user.id,
        text=text,
        tg_forward_status="pending",
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
