"""Task 24: CRUD for saved catalog searches (cabinet)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services import saved_searches as ss
from app.utils.security import get_current_user

router = APIRouter(prefix="/saved-searches", tags=["saved-searches"])


class SavedSearchIn(BaseModel):
    name: str | None = Field(None, max_length=100)
    filters: dict = Field(default_factory=dict)


class SavedSearchOut(BaseModel):
    id: int
    name: str
    filters: dict
    created_at: str | None = None
    last_delivery_status: str | None = None

    model_config = {"from_attributes": True}


def _out(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "filters": row.filters or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_delivery_status": row.last_delivery_status,
    }


@router.get("")
async def list_saved(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await ss.list_for_user(db, user.id)
    return {"items": [_out(r) for r in rows], "max": ss.MAX_PER_USER}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_saved(body: SavedSearchIn, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    try:
        row = await ss.create_for_user(db, user, name=body.name, filters=body.filters)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Максимум {ss.MAX_PER_USER} збережених пошуків")
    return _out(row)


@router.delete("/{search_id}")
async def delete_saved(search_id: int, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if not await ss.delete_for_user(db, user.id, search_id):
        raise HTTPException(status_code=404, detail="Пошук не знайдено")
    return {"ok": True}
