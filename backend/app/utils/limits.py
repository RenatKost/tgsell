"""Єдиний ліміт ціни для полів create/update (лоти, сітки, аукціони, ставки, бюджет «Шукаю канал», зовнішній гарант).

Застосовується ЛИШЕ до вхідних схем (create/update) — схеми відповіді/читання старих записів не валідуються.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

MAX_PRICE_USDT: float = 10_000_000.0
MAX_PRICE_MSG = "Максимальна ціна — 10\u00a0000\u00a0000 USDT"


class PriceTooHigh(ValueError):
    pass


def check_max_price(v: float | None) -> float | None:
    """Pydantic validator helper: None пропускається, > MAX_PRICE_USDT → ValueError з українським текстом."""
    if v is not None and v == v and v > MAX_PRICE_USDT:
        raise PriceTooHigh(MAX_PRICE_MSG)
    return v


def install_price_limit_handler(app: FastAPI) -> None:
    """422 з плоским українським detail для порушення ліміту ціни; решта помилок — стандартна обробка FastAPI."""

    @app.exception_handler(RequestValidationError)
    async def _handler(request: Request, exc: RequestValidationError):
        for err in exc.errors():
            if MAX_PRICE_MSG in str(err.get("msg", "")):
                return JSONResponse(status_code=422, content={"detail": MAX_PRICE_MSG})
        return await request_validation_exception_handler(request, exc)
