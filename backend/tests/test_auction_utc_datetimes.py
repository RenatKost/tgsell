from datetime import datetime, timedelta, timezone

from app.schemas.auction import AuctionBidResponse, AuctionDetailResponse
from app.utils.timeutil import to_utc_iso

NAIVE = datetime(2026, 11, 5, 18, 15, 53, 539486)


def _auction(**kw):
    base = dict(id=27, channel_id=103, seller_id=62, start_price=1100, bid_step=50,
                current_price=1100, buyout_price=None, status="active",
                starts_at=NAIVE, ends_at=NAIVE, winner_id=None, bid_count=0, created_at=NAIVE)
    base.update(kw)
    return AuctionDetailResponse(**base)


def test_to_utc_iso_naive_and_aware():
    assert to_utc_iso(None) is None
    assert to_utc_iso(NAIVE) == "2026-11-05T18:15:53.539486Z"
    aware = datetime(2026, 11, 5, 20, 0, tzinfo=timezone(timedelta(hours=2)))
    assert to_utc_iso(aware) == "2026-11-05T18:00:00Z"


def test_auction_json_has_z_no_double():
    a = _auction(bids=[AuctionBidResponse(id=1, auction_id=27, bidder_id=1, amount=1150, created_at=NAIVE)])
    d = a.model_dump(mode="json")
    for k in ("starts_at", "ends_at", "created_at"):
        assert d[k] == "2026-11-05T18:15:53.539486Z"
        assert d[k].count("Z") == 1
    assert d["bids"][0]["created_at"].endswith("Z")
    assert '"ends_at":"2026-11-05T18:15:53.539486Z"' in a.model_dump_json()


def test_channel_top_until_and_auction_end_z():
    from app.schemas.channel import ChannelResponse
    fields = ChannelResponse.model_fields
    assert "top_until" in fields and "active_auction_ends_at" in fields
    from pydantic import TypeAdapter
    for name in ("top_until", "active_auction_ends_at"):
        ta = TypeAdapter(fields[name].rebuild_annotation())
        assert ta.dump_python(NAIVE, mode="json") == "2026-11-05T18:15:53.539486Z"
        assert ta.dump_python(None, mode="json") is None


def test_channel_created_at_z():
    from app.schemas.channel import ChannelResponse
    from pydantic import TypeAdapter
    ta = TypeAdapter(ChannelResponse.model_fields["created_at"].rebuild_annotation())
    assert ta.dump_python(NAIVE, mode="json") == "2026-11-05T18:15:53.539486Z"
    ch = ChannelResponse(
        id=1, seller_id=1, telegram_link="https://t.me/x", channel_name="X",
        seller_telegram=None, category="x", subscribers_count=1, price=1.0,
        monthly_income=None, description=None, resources=None, avatar_url=None,
        avg_views=None, er=None, daily_growth=None, age=None,
        adv_reach_12h=None, adv_reach_24h=None, adv_reach_48h=None,
        status="approved", created_at=NAIVE,
    )
    assert ch.model_dump(mode="json")["created_at"] == "2026-11-05T18:15:53.539486Z"
    assert ch.model_dump(mode="json")["created_at"].endswith("Z")


def test_bundle_user_deal_created_at_z():
    from app.schemas.auth import UserResponse, PublicUserProfile
    from app.schemas.bundle import BundleResponse
    from app.schemas.deal import DealResponse, DealMessageResponse
    from pydantic import TypeAdapter
    for schema, field in (
        (UserResponse, "created_at"),
        (PublicUserProfile, "created_at"),
        (BundleResponse, "created_at"),
        (DealResponse, "created_at"),
        (DealMessageResponse, "created_at"),
    ):
        ta = TypeAdapter(schema.model_fields[field].rebuild_annotation())
        assert ta.dump_python(NAIVE, mode="json") == "2026-11-05T18:15:53.539486Z"
