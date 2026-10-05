"""Money-safety: payout claim race — transfer_usdt at most once under concurrency.

Runs without DB/network: stubs app.database; mocks transfer_usdt.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_db_stub() -> None:
    if "app.database" in sys.modules:
        return
    stub = ModuleType("app.database")

    class Base:  # noqa: D401
        pass

    stub.Base = Base
    stub.async_session = None
    stub.get_db = None
    sys.modules["app.database"] = stub


_install_db_stub()

from app.models.deal import DealStatus  # noqa: E402
from app.services.deal_lifecycle import (  # noqa: E402
    PayoutClaimError,
    claim_deal_for_transfer,
    has_payout_tx,
    mark_deal_completed,
    release_payout_claim,
)


def _fake_deal(**kwargs):
    base = dict(
        id=42,
        status=DealStatus.awaiting_payout,
        payout_tx_hash=None,
        completed_at=None,
        seller_payout_address=None,
        amount_usdt=100.0,
        service_fee=3.0,
        escrow_wallet_address="TEscrowWalletAddressXXXXX",
        escrow_private_key_encrypted="encrypted-key",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_claim_sets_payout_in_progress():
    deal = _fake_deal()
    claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    assert deal.status == DealStatus.payout_in_progress


def test_claim_rejects_wrong_status():
    deal = _fake_deal(status=DealStatus.disputed)
    with pytest.raises(PayoutClaimError) as ei:
        claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    assert ei.value.http_status == 400
    assert ei.value.code == "wrong_status"


def test_claim_rejects_already_in_progress():
    deal = _fake_deal(status=DealStatus.payout_in_progress)
    with pytest.raises(PayoutClaimError) as ei:
        claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    assert ei.value.http_status == 409
    assert ei.value.code == "in_progress"


def test_claim_rejects_when_payout_tx_hash_set():
    deal = _fake_deal(payout_tx_hash="already_sent_txid")
    with pytest.raises(PayoutClaimError) as ei:
        claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    assert ei.value.http_status == 409
    assert ei.value.code == "already_paid"


def test_second_claim_after_first_gets_409():
    deal = _fake_deal()
    claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    with pytest.raises(PayoutClaimError) as ei:
        claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    assert ei.value.http_status == 409


def test_release_claim_restores_awaiting_payout():
    deal = _fake_deal()
    claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    release_payout_claim(deal, restore_status=DealStatus.awaiting_payout)
    assert deal.status == DealStatus.awaiting_payout


def test_admin_claim_from_disputed():
    deal = _fake_deal(status=DealStatus.disputed)
    claim_deal_for_transfer(deal, expected_status=DealStatus.disputed)
    assert deal.status == DealStatus.payout_in_progress


def test_has_payout_tx():
    assert has_payout_tx(_fake_deal(payout_tx_hash="abc")) is True
    assert has_payout_tx(_fake_deal(payout_tx_hash="  ")) is False
    assert has_payout_tx(_fake_deal(payout_tx_hash=None)) is False


@pytest.mark.asyncio
async def test_concurrent_claims_transfer_called_at_most_once():
    """Simulate FOR UPDATE with an asyncio.Lock; only the winner may transfer."""
    deal = _fake_deal(status=DealStatus.awaiting_payout)
    row_lock = asyncio.Lock()
    transfer_mock = MagicMock(return_value="txid_once")
    results: list[tuple[str, int]] = []

    async def one_request() -> None:
        # Mimic router: lock → claim → commit(release lock) → transfer
        try:
            async with row_lock:
                claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
                # "commit" happens before lock release — status already payout_in_progress
            await asyncio.sleep(0.02)  # stand-in for gas sleep AFTER claim
            tx = transfer_mock(deal.escrow_private_key_encrypted, "TSellerWallet", 97.0)
            mark_deal_completed(deal, tx)
            results.append(("ok", 200))
        except PayoutClaimError as e:
            results.append(("reject", e.http_status))

    await asyncio.gather(one_request(), one_request(), one_request())

    assert transfer_mock.call_count == 1
    oks = [r for r in results if r[0] == "ok"]
    rejects = [r for r in results if r[0] == "reject"]
    assert len(oks) == 1
    assert len(rejects) == 2
    assert all(code == 409 for _, code in rejects)
    assert deal.status == DealStatus.completed
    assert deal.payout_tx_hash == "txid_once"


@pytest.mark.asyncio
async def test_concurrent_admin_resolve_transfer_once():
    deal = _fake_deal(status=DealStatus.disputed)
    row_lock = asyncio.Lock()
    transfer_mock = MagicMock(return_value="admin_txid")
    results: list[tuple[str, int]] = []

    async def one_resolve() -> None:
        try:
            async with row_lock:
                claim_deal_for_transfer(deal, expected_status=DealStatus.disputed)
            await asyncio.sleep(0.01)
            tx = transfer_mock(deal.escrow_private_key_encrypted, "TBuyerWallet", 100.0)
            deal.payout_tx_hash = tx
            deal.status = DealStatus.cancelled
            results.append(("ok", 200))
        except PayoutClaimError as e:
            results.append(("reject", e.http_status))

    await asyncio.gather(one_resolve(), one_resolve())
    assert transfer_mock.call_count == 1
    assert sorted(r[0] for r in results) == ["ok", "reject"]
    assert results[0][1] in (200, 409) and results[1][1] in (200, 409)


@pytest.mark.asyncio
async def test_failed_transfer_releases_claim_no_blind_retry():
    """On transfer failure: restore awaiting_payout; do not call transfer again."""
    deal = _fake_deal()
    transfer_mock = MagicMock(return_value=None)

    claim_deal_for_transfer(deal, expected_status=DealStatus.awaiting_payout)
    assert deal.status == DealStatus.payout_in_progress

    tx = transfer_mock("key", "TWallet", 97.0)
    assert tx is None
    release_payout_claim(deal, restore_status=DealStatus.awaiting_payout)
    assert deal.status == DealStatus.awaiting_payout
    assert transfer_mock.call_count == 1  # no blind retry after release


def test_enum_has_payout_in_progress():
    assert DealStatus.payout_in_progress.value == "payout_in_progress"


def test_migration_0021_adds_enum_value():
    mig = (BACKEND_ROOT / "alembic/versions/0021_add_payout_in_progress.py").read_text(
        encoding="utf-8"
    )
    assert "payout_in_progress" in mig
    assert "ALTER TYPE dealstatus" in mig
    assert 'down_revision' in mig and "0020" in mig


def test_seller_wallet_uses_for_update_and_claim():
    src = (BACKEND_ROOT / "app/routers/deals.py").read_text(encoding="utf-8")
    assert "with_for_update()" in src
    assert "claim_deal_for_transfer" in src
    assert "payout_in_progress" in src or "claim_deal_for_transfer" in src
    # sleep must not precede claim
    fn_start = src.index("async def set_seller_wallet")
    fn_end = src.index("async def call_admin", fn_start)
    body = src[fn_start:fn_end]
    claim_pos = body.index("claim_deal_for_transfer")
    commit_claim_pos = body.index("await db.commit()", claim_pos)
    sleep_pos = body.index("asyncio.sleep", commit_claim_pos)
    transfer_pos = body.index("transfer_usdt(", commit_claim_pos)
    assert claim_pos < commit_claim_pos < sleep_pos
    assert commit_claim_pos < transfer_pos


def test_admin_resolve_uses_for_update_and_claim():
    src = (BACKEND_ROOT / "app/routers/admin.py").read_text(encoding="utf-8")
    fn_start = src.index("async def resolve_deal")
    fn_end = src.index("_FUNDED_DEAL_STATUSES", fn_start)
    body = src[fn_start:fn_end]
    assert "with_for_update()" in body
    assert "claim_deal_for_transfer" in body
    assert "DealStatus.disputed" in body
    claim_pos = body.index("claim_deal_for_transfer")
    commit_pos = body.index("await db.commit()", claim_pos)
    transfer_pos = body.index("_escrow_transfer_usdt", commit_pos)
    assert claim_pos < commit_pos < transfer_pos
