"""Task 15 item 3: amounts/fees are serialized with 2 decimals (display only)."""
from datetime import datetime

from app.schemas.deal import DealResponse
from app.utils.money_display import money2, money2_str


def _deal(**kw):
    base = dict(id=26, buyer_id=1, seller_id=2, status="created", escrow_wallet_address="T",
                amount_usdt=15.0, service_fee=15.0 * 0.03, deal_group_chat_id=None, dispute_reason=None,
                created_at=datetime(2026, 10, 1), paid_at=None, completed_at=None)
    base.update(kw)
    return DealResponse(**base)


def test_money2_half_up():
    assert money2(0.45000000000000007) == 0.45
    assert money2(1.005) == 1.01  # float 1.005 is 1.00499..; str() keeps it HALF_UP
    assert money2(2.675) == 2.68
    assert money2(None) is None
    assert money2_str(3) == "3.00"


def test_deal_response_rounds_fee_and_amount():
    d = _deal(amount_usdt=33.333333, service_fee=33.333333 * 0.03, received_usdt=12.345678)
    js = d.model_dump(mode="json")
    assert js["service_fee"] == 1.0 and js["amount_usdt"] == 33.33
    assert d.service_fee == 33.333333 * 0.03  # underlying value untouched
    assert js["received_usdt"] == 12.345678  # on-chain received amount stays precise
    assert '"service_fee":0.45' in _deal().model_dump_json()
