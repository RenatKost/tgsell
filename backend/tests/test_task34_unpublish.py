"""Task 34: unpublish test bundle #1 and lot #61 (data migration 0045) + /bundle/:id noindex meta."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.utils import spa_meta

MIG = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0045_unpublish_test_bundle_and_lot61.py"


def _mig():
    spec = importlib.util.spec_from_file_location("mig0045", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_chain_and_no_delete():
    m = _mig()
    assert m.revision == "0045" and m.down_revision == "0044"
    assert "DELETE" not in MIG.read_text(encoding="utf-8").upper()


@pytest.mark.parametrize("st", ["pending", "rejected"])
def test_unpublished_bundle_meta_noindex(st):
    meta = spa_meta.bundle_meta(SimpleNamespace(status=st, name="Крипто медіа", price=3000))
    assert meta["noindex"] and "Крипто" not in meta["title"] + meta["description"]


def test_bundle_meta_public_and_unknown():
    assert spa_meta.bundle_meta(None)["noindex"]
    meta = spa_meta.bundle_meta(SimpleNamespace(status="approved", name="X", price=10))
    assert not meta.get("noindex") and "X" in meta["title"]
    assert spa_meta.bundle_id_from_path("bundle/1") == 1
    assert spa_meta.bundle_id_from_path("channel/1") is None


@pytest.mark.asyncio
async def test_migration_unpublishes_only_targets(pg_orm):
    from app.models.bundle import BundleChannel, BundleStatus, ChannelBundle
    from app.models.channel import Channel, ChannelStatus
    from app.models.user import User, UserRole

    async with pg_orm.session() as db:
        u = User(first_name="S", telegram_id=734001, role=UserRole.user)
        db.add(u)
        await db.flush()
        for i in list(range(15, 19)) + [61, 62]:
            link = "https://t.me/kriptoludis" if i == 61 else f"https://t.me/c{i}"
            db.add(Channel(id=i, seller_id=u.id, telegram_link=link, channel_name=f"c{i}", category="x",
                           price=0 if i < 19 else 10, status=ChannelStatus.approved))
        db.add_all([ChannelBundle(id=1, seller_id=u.id, name="Крипто медіа", price=3000, status=BundleStatus.approved),
                    ChannelBundle(id=2, seller_id=u.id, name="Other", price=1, status=BundleStatus.approved)])
        await db.flush()
        db.add_all([BundleChannel(bundle_id=1, channel_id=i, display_order=i) for i in range(15, 19)])
        await db.commit()

    m = _mig()
    for _ in range(2):  # idempotent
        async with pg_orm.engine.begin() as conn:
            await conn.run_sync(m.unpublish)

    async with pg_orm.session() as db:
        bs = {b.id: b for b in (await db.execute(select(ChannelBundle))).scalars()}
        cs = {c.id: c for c in (await db.execute(select(Channel))).scalars()}
        links = (await db.execute(select(BundleChannel))).scalars().all()
    assert bs[1].status == BundleStatus.rejected and bs[1].rejection_reason
    assert bs[2].status == BundleStatus.approved
    assert cs[61].status == ChannelStatus.removed and cs[61].removed_at and cs[61].removed_reason
    assert cs[62].status == ChannelStatus.approved
    assert all(cs[i].status == ChannelStatus.approved for i in range(15, 19))
    assert len(links) == 4 and len(bs) == 2 and len(cs) == 6
