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


def to_utc_iso(value: datetime | None) -> str | None:
    """Serialize a datetime as ISO 8601 UTC with a ``Z`` suffix.

    Naive values are treated as UTC (DB columns store naive UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(tzinfo=None).isoformat() + "Z"


# Reusable pydantic type: a datetime that always serializes as "...Z" (UTC).
from typing import Annotated  # noqa: E402

from pydantic import PlainSerializer  # noqa: E402

UTCDateTime = Annotated[
    datetime,
    PlainSerializer(to_utc_iso, return_type=str, when_used="json-unless-none"),
]
