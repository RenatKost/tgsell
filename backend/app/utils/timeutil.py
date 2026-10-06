"""Datetime helpers for DB writes.

Most DB columns are ``DateTime`` (TIMESTAMP WITHOUT TIME ZONE) and store naive
UTC values. asyncpg refuses to bind a timezone-aware ``datetime`` to such a
column (``can't subtract offset-naive and offset-aware datetimes``), so every
value written into / compared against a naive column must have ``tzinfo=None``.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """Current UTC time as a naive datetime (same value as ``datetime.utcnow()``,
    without the 3.12 deprecation warning). Use for naive ``DateTime`` columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """Convert an aware datetime to naive UTC; naive values are returned as-is
    (assumed to already be UTC)."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
