"""Money-safety: completed deals must have a real payout_tx_hash.

Runs without DB/network: stubs app.database before importing models.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_db_stub() -> None:
    """Avoid create_async_engine / asyncpg import side-effects during unit tests."""
    if "app.database" in sys.modules:
        return
    stub = ModuleType("app.database")

    class Base:  # noqa: D401 — minimal DeclarativeBase stand-in
        pass

    stub.Base = Base
    stub.async_session = None
    stub.get_db = None
    sys.modules["app.database"] = stub


_install_db_stub()

from app.models.deal import DealStatus  # noqa: E402
from app.services.deal_lifecycle import (  # noqa: E402
    DealCompletionError,
    assert_completed_has_payout,
    mark_deal_completed,
)


def _fake_deal(**kwargs):
    base = dict(
        id=1,
        status=DealStatus.awaiting_payout,
        payout_tx_hash=None,
        completed_at=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_mark_deal_completed_rejects_none():
    deal = _fake_deal()
    with pytest.raises(DealCompletionError):
        mark_deal_completed(deal, None)


def test_mark_deal_completed_rejects_empty_string():
    deal = _fake_deal()
    with pytest.raises(DealCompletionError):
        mark_deal_completed(deal, "")


def test_mark_deal_completed_rejects_whitespace():
    deal = _fake_deal()
    with pytest.raises(DealCompletionError):
        mark_deal_completed(deal, "   ")


def test_mark_deal_completed_sets_status_and_hash():
    deal = _fake_deal()
    mark_deal_completed(deal, "abc123txid")
    assert deal.status == DealStatus.completed
    assert deal.payout_tx_hash == "abc123txid"
    assert deal.completed_at is not None
    assert_completed_has_payout(deal)


def test_assert_completed_has_payout_raises_when_missing():
    deal = _fake_deal(status=DealStatus.completed, payout_tx_hash=None)
    with pytest.raises(DealCompletionError):
        assert_completed_has_payout(deal)


def _assignments_to_completed(py_path: Path) -> list[tuple[int, str]]:
    """Find AST assignments of DealStatus.completed."""
    src = py_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(py_path))
    hits: list[tuple[int, str]] = []

    class Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign):
            val = node.value
            if (
                isinstance(val, ast.Attribute)
                and val.attr == "completed"
                and isinstance(val.value, ast.Name)
                and val.value.id == "DealStatus"
            ):
                hits.append((node.lineno, ast.get_source_segment(src, node) or ""))
            self.generic_visit(node)

    Visitor().visit(tree)
    return hits


def test_no_direct_completed_assignment_outside_lifecycle():
    """Regression: previous bad paths assigned completed without payout.

    Allowed: only app/services/deal_lifecycle.py may assign DealStatus.completed.
    """
    offenders: list[str] = []
    for root_name in ("app", "bot"):
        root = BACKEND_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.name == "deal_lifecycle.py":
                continue
            for lineno, segment in _assignments_to_completed(path):
                offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{lineno}: {segment}")

    assert not offenders, (
        "Direct DealStatus.completed assignments found (must use mark_deal_completed):\n"
        + "\n".join(offenders)
    )


def test_bot_confirm_does_not_set_completed():
    bot_main = (BACKEND_ROOT / "bot/main.py").read_text(encoding="utf-8")
    assert "deal.status = DealStatus.completed" not in bot_main
    assert "DealStatus.awaiting_payout" in bot_main
    assert "TODO: Trigger USDT release" not in bot_main


def test_admin_resolve_no_longer_has_todo_without_transfer():
    admin = (BACKEND_ROOT / "app/routers/admin.py").read_text(encoding="utf-8")
    assert "# TODO: refund USDT to buyer" not in admin
    assert "# TODO: release USDT to seller" not in admin
    assert "mark_deal_completed" in admin
    assert "_escrow_transfer_usdt" in admin
