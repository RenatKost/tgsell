"""Єдиний ліміт ціни 10 000 000 USDT: лише create/update, 422 з українським текстом, читання не валідується."""

import pytest
from fastapi import Body, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.utils.limits import MAX_PRICE_MSG, MAX_PRICE_USDT, check_max_price, install_price_limit_handler


def test_constant_and_message():
    assert MAX_PRICE_USDT == 10_000_000
    assert "10\u00a0000\u00a0000 USDT" in MAX_PRICE_MSG and MAX_PRICE_MSG.startswith("Максимальна ціна")


@pytest.mark.parametrize("v", [None, 0.01, 1, 9_999_999.99, MAX_PRICE_USDT])
def test_check_allows(v):
    assert check_max_price(v) == v


def test_check_rejects():
    with pytest.raises(ValueError, match="Максимальна ціна"):
        check_max_price(MAX_PRICE_USDT + 0.01)


def _base_channel(**kw):
    d = dict(telegram_link="https://t.me/x", category="Крипта", price=100)
    d.update(kw)
    return d


@pytest.mark.parametrize("field", ["price", "auction_start_price", "auction_bid_step"])
def test_channel_create_limit(field):
    from app.schemas.channel import ChannelCreate
    ChannelCreate(**_base_channel(**{field: MAX_PRICE_USDT}))
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        ChannelCreate(**_base_channel(**{field: 100_000_000}))


def test_channel_update_limit():
    from app.schemas.channel import ChannelUpdate
    assert ChannelUpdate().price is None
    ChannelUpdate(price=MAX_PRICE_USDT)
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        ChannelUpdate(price=10_000_001)


def test_bundle_limits():
    from app.schemas.bundle import BundleCreate, BundleUpdate
    base = dict(name="Сітка", price=MAX_PRICE_USDT, channel_links=["t.me/a", "t.me/b"])
    BundleCreate(**base)
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        BundleCreate(**{**base, "price": 10_000_001})
    with pytest.raises(ValidationError, match="Price must be positive"):
        BundleCreate(**{**base, "price": 0})
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        BundleUpdate(price=50_000_000)


def test_bid_limit():
    from app.schemas.auction import AuctionBidCreate
    AuctionBidCreate(amount=MAX_PRICE_USDT)
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        AuctionBidCreate(amount=MAX_PRICE_USDT * 2)


def test_wanted_and_escrow_input_limits():
    from app.routers.external_escrow import OfferIn
    from app.routers.wanted import WantedIn
    WantedIn(category="Крипта", language="ua", budget_max=MAX_PRICE_USDT)
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        WantedIn(category="Крипта", language="ua", budget_max=20_000_000)
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        WantedIn(category="Крипта", language="ua", budget_min=20_000_000, budget_max=1)
    with pytest.raises(ValidationError, match="Максимальна ціна"):
        OfferIn(channel_link="t.me/x", price_usdt=100_000_000, buyer_username="b")


def test_escrow_own_stricter_limit_unchanged():
    from app.services import external_escrow as svc
    assert svc.MAX_PRICE_USDT == 1_000_000.0


def test_response_schemas_not_validated():
    """Старі записи з ціною > ліміту читаються без помилок (валідація лише на вході)."""
    from app.schemas.auction import AuctionBidResponse
    from app.schemas.channel import ChannelResponse
    for model in (ChannelResponse, AuctionBidResponse):
        for name, f in model.model_fields.items():
            if name in ("price", "amount"):
                assert "check_max_price" not in repr(model.__pydantic_decorators__.field_validators)


@pytest.mark.asyncio
async def test_handler_returns_flat_ukrainian_422_and_keeps_default():
    from app.schemas.channel import ChannelUpdate
    app = FastAPI()
    install_price_limit_handler(app)

    @app.put("/x")
    async def x(body: ChannelUpdate):
        return {"ok": True}

    @app.put("/y")
    async def y(n: int = Body(..., embed=True)):
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.put("/x", json={"price": 100_000_000})
        assert r.status_code == 422 and r.json() == {"detail": MAX_PRICE_MSG}
        r = await c.put("/x", json={"price": 9_999_999.99})
        assert r.status_code == 200
        r = await c.put("/y", json={"n": "abc"})
        assert r.status_code == 422 and r.json()["detail"] == "Некоректні дані запиту"


def test_main_app_installs_handler():
    import importlib
    main = importlib.import_module("app.main")
    from fastapi.exceptions import RequestValidationError
    assert RequestValidationError in main.app.exception_handlers
