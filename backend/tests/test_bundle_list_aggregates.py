from types import SimpleNamespace
from datetime import datetime

from app.models.bundle import BundleStatus
from app.routers.bundles import _bundle_to_response


def _ch(i, subs, er, views=None):
    return SimpleNamespace(id=i, channel_name=f"c{i}", telegram_link="x", avatar_url=None,
                           subscribers_count=subs, avg_views=views, er=er, category="Новини",
                           stars_balance=None, ton_balance=None, is_closed=er is None,
                           monthly_income=None)


def test_list_response_has_aggregates():
    b = SimpleNamespace(id=6, seller_id=1, name="b", description=None, category=None,
                        price=1.0, monthly_income=None, resources=None,
                        status=BundleStatus.approved, rejection_reason=None,
                        created_at=datetime.now(), moderated_at=None,
                        bundle_channels=[SimpleNamespace(channel=c) for c in
                                         (_ch(97, 236957, 8.54, 20228), _ch(98, 167640, None), _ch(99, 150382, 8.36, 12565))])
    r = _bundle_to_response(b)
    assert r.total_subscribers == 554979
    assert r.avg_er is not None and 8.0 < r.avg_er < 9.0
    assert r.monthly_income is None
