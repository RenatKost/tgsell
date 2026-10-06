"""Pytest fixtures shared across backend tests (DB harness lives in db_harness.py)."""
from tests.db_harness import db_url, orm, pg_orm  # noqa: F401
