"""Activity stats & feed — real data + organic-looking baseline for gamification."""
import hashlib
import logging
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.auction import Auction, AuctionBid
from app.models.channel import Channel
from app.models.deal import Deal
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])

# --- Ukrainian name pool for generated events ---
_FIRST_NAMES = [
    "Олександр", "Андрій", "Максим", "Дмитро", "Артем", "Іван", "Микола",
    "Владислав", "Юрій", "Богдан", "Тарас", "Сергій", "Віталій", "Роман",
    "Олена", "Анна", "Марія", "Катерина", "Наталія", "Юлія", "Вікторія",
    "Ірина", "Тетяна", "Оксана", "Дарина", "Софія", "Аліна", "Діана",
]

_CHANNEL_NAMES = [
    "Крипто UA", "Новини 24/7", "Tech Insider", "Бізнес клуб",
    "Мотивація", "Фінанси просто", "Маркетинг Pro", "IT новини",
    "Авто Україна", "Спорт Live", "Кулінарія", "Подорожі",
    "Книги UA", "Музика", "Gaming Zone", "Здоров'я+",
    "Інвестиції", "Стартапи", "Дизайн", "Фотографія",
]


def _seed_random(seed_str: str) -> random.Random:
    """Deterministic Random seeded by string (same seed = same output)."""
    h = hashlib.md5(seed_str.encode()).hexdigest()
    return random.Random(int(h, 16))


def _hour_factor(hour: int) -> float:
    """Activity multiplier by hour of day (Ukraine timezone ~UTC+2)."""
    # Peak: 10-22 local (~8-20 UTC), low: 0-7 UTC
    if 8 <= hour <= 20:
        return 1.0
    elif 6 <= hour <= 22:
        return 0.6
    else:
        return 0.3


@router.get("/activity")
async def get_activity_stats(db: AsyncSession = Depends(get_db)):
    """Boosted activity stats. Offsets auto-shrink as real data grows."""
    from app.routers.admin import get_activity_config
    config = get_activity_config()

    if not config.get("enabled", True):
        # Return real-only stats
        real_channels = (await db.execute(
            select(func.count()).select_from(Channel).where(Channel.status == "approved")
        )).scalar() or 0
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        real_deals_week = (await db.execute(
            select(func.count()).select_from(Deal).where(Deal.created_at >= week_ago)
        )).scalar() or 0
        real_bids_today = (await db.execute(
            select(func.count()).select_from(AuctionBid).where(AuctionBid.created_at >= today_start)
        )).scalar() or 0
        real_active_auctions = (await db.execute(
            select(func.count()).select_from(Auction).where(Auction.status == "active")
        )).scalar() or 0
        return {
            "channels_count": real_channels,
            "online_investors": 0,
            "deals_this_week": real_deals_week,
            "bids_today": real_bids_today,
            "active_auctions": real_active_auctions,
        }

    now = datetime.utcnow()
    seed_str = f"{now.strftime('%Y-%m-%d-%H')}"
    rng = _seed_random(seed_str)
    hour_mult = _hour_factor(now.hour)

    # Real counts
    real_channels = (await db.execute(
        select(func.count()).select_from(Channel).where(Channel.status == "approved")
    )).scalar() or 0

    week_ago = now - timedelta(days=7)
    real_deals_week = (await db.execute(
        select(func.count()).select_from(Deal).where(Deal.created_at >= week_ago)
    )).scalar() or 0

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    real_bids_today = (await db.execute(
        select(func.count()).select_from(AuctionBid).where(AuctionBid.created_at >= today_start)
    )).scalar() or 0

    real_active_auctions = (await db.execute(
        select(func.count()).select_from(Auction).where(Auction.status == "active")
    )).scalar() or 0

    # Boosted values — offset shrinks as real grows
    def boosted(real: int, base_min: int, base_max: int) -> int:
        base = rng.randint(base_min, base_max)
        base = int(base * hour_mult)
        offset = max(0, base - real * 2)
        return real + offset

    return {
        "channels_count": boosted(real_channels, config["channels_min"], config["channels_max"]),
        "online_investors": boosted(0, config["online_investors_min"], config["online_investors_max"]),
        "deals_this_week": boosted(real_deals_week, config["deals_week_min"], config["deals_week_max"]),
        "bids_today": boosted(real_bids_today, config["bids_today_min"], config["bids_today_max"]),
        "active_auctions": boosted(real_active_auctions, config["active_auctions_min"], config["active_auctions_max"]),
    }


@router.get("/feed")
async def get_activity_feed(db: AsyncSession = Depends(get_db)):
    """Mixed real + generated events feed. All events look identical."""
    from app.routers.admin import get_activity_config
    config = get_activity_config()

    now = datetime.utcnow()
    events = []

    # --- Real events ---
    # Recent deals
    result = await db.execute(
        select(Deal).order_by(Deal.created_at.desc()).limit(5)
    )
    for deal in result.scalars().all():
        buyer = await db.get(User, deal.buyer_id)
        events.append({
            "type": "deal_completed",
            "text": f"💰 {buyer.first_name if buyer else 'Користувач'} придбав канал за {int(deal.amount_usdt)} USDT",
            "created_at": deal.created_at.isoformat(),
        })

    # Recent auction bids
    result = await db.execute(
        select(AuctionBid).order_by(AuctionBid.created_at.desc()).limit(5)
    )
    for bid in result.scalars().all():
        bidder = await db.get(User, bid.bidder_id)
        events.append({
            "type": "auction_bid",
            "text": f"🔥 {bidder.first_name if bidder else 'Інвестор'} зробив ставку {int(bid.amount)} USDT",
            "created_at": bid.created_at.isoformat(),
        })

    # Recent channels
    result = await db.execute(
        select(Channel)
        .where(Channel.status == "approved")
        .order_by(Channel.created_at.desc())
        .limit(5)
    )
    for ch in result.scalars().all():
        events.append({
            "type": "new_channel",
            "text": f"📊 Канал «{ch.channel_name}» додано в каталог",
            "created_at": ch.created_at.isoformat(),
        })

    # --- Generated events to fill gaps ---
    gen_count = config.get("feed_generated_count", 15) if config.get("enabled", True) else 0
    seed_str = f"{now.strftime('%Y-%m-%d')}"
    rng = _seed_random(seed_str)

    # Generate events spread across the day
    for i in range(gen_count):
        event_rng = _seed_random(f"{seed_str}-{i}")
        # Non-uniform gaps: 3-15 min apart
        minutes_ago = sum(event_rng.randint(3, 15) for _ in range(i + 1))
        event_time = now - timedelta(minutes=minutes_ago)

        name = event_rng.choice(_FIRST_NAMES)
        event_type = event_rng.choice(["deal_completed", "auction_bid", "new_channel", "new_user"])

        if event_type == "deal_completed":
            amount = event_rng.choice([200, 350, 500, 750, 1000, 1500, 2000, 3000, 5000])
            text = f"💰 {name} придбав канал за {amount} USDT"
        elif event_type == "auction_bid":
            amount = event_rng.choice([100, 250, 400, 600, 800, 1200, 1800])
            text = f"🔥 {name} зробив ставку {amount} USDT"
        elif event_type == "new_channel":
            ch_name = event_rng.choice(_CHANNEL_NAMES)
            text = f"📊 Канал «{ch_name}» додано в каталог"
        else:
            text = f"👤 {name} приєднався до платформи"

        events.append({
            "type": event_type,
            "text": text,
            "created_at": event_time.isoformat(),
        })

    # Sort by time desc and return top 20
    events.sort(key=lambda e: e["created_at"], reverse=True)
    return events[:20]
