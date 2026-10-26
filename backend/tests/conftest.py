"""Pytest fixtures shared across backend tests (DB harness lives in db_harness.py)."""
import os

# Tests must not depend on the developer's shell. Real CatFee credentials in the environment
# (CATFEE_API_KEY / CATFEE_API_SECRET / CATFEE_BASE_URL) switch payouts, refunds and fee sweeps
# onto the live CatFee energy-rental path, which makes ~39 money/chat/blocking tests fail with
# PREPARE_ERROR. Drop them before app.config.Settings is first instantiated; tests that need
# CatFee set it explicitly via monkeypatch.
for _k in [k for k in os.environ if k.upper().startswith("CATFEE_")]:
    os.environ.pop(_k, None)

from tests.db_harness import db_url, orm, pg_orm  # noqa: E402,F401
