"""422: short Ukrainian detail + field names only; no pydantic internals."""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_422_is_generic_and_has_no_internals():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
        r = await cl.post("/api/track/funnel", json={"utm_source": "x" * 500})
    assert r.status_code == 422
    body = r.json()
    assert body["detail"] == "Некоректні дані запиту"
    assert set(body["fields"]) == {"event", "utm_source"}
    t = r.text
    for bad in ("pydantic", "errors.pydantic.dev", "\"type\"", "\"input\"", "\"loc\"", "xxxx"):
        assert bad not in t


def test_price_limit_message_kept():
    from app.utils.limits import MAX_PRICE_MSG
    assert "USDT" in MAX_PRICE_MSG
