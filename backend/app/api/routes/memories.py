"""Opt-in long-term memory: things the user approved Dhanz to remember."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, parse_uuid
from app.db.base import utcnow
from app.models import Memory
from app.schemas import MemoryCreate, MemoryOut

router = APIRouter(prefix="/memories", tags=["memory"])

MAX_MEMORIES = 200


async def _owned(db, user, memory_id: str) -> Memory:
    memory = await db.get(Memory, parse_uuid(memory_id))
    if memory is None or memory.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")
    return memory


@router.get("", response_model=list[MemoryOut])
async def list_memories(user: CurrentUser, db: DbDep) -> list[Memory]:
    return list(await db.scalars(select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at)))


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def add_memory(body: MemoryCreate, user: CurrentUser, db: DbDep) -> Memory:
    count = len(list(await db.scalars(select(Memory.id).where(Memory.user_id == user.id))))
    if count >= MAX_MEMORIES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You can keep up to {MAX_MEMORIES} memories. Delete some first.")
    memory = Memory(user_id=user.id, content=body.content.strip(), source="manual")
    db.add(memory)
    await db.commit()
    return memory


@router.patch("/{memory_id}", response_model=MemoryOut)
async def edit_memory(memory_id: str, body: MemoryCreate, user: CurrentUser, db: DbDep) -> Memory:
    memory = await _owned(db, user, memory_id)
    memory.content = body.content.strip()
    memory.updated_at = utcnow()
    await db.commit()
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str, user: CurrentUser, db: DbDep) -> Response:
    memory = await _owned(db, user, memory_id)
    await db.delete(memory)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_memories(user: CurrentUser, db: DbDep) -> Response:
    for memory in await db.scalars(select(Memory).where(Memory.user_id == user.id)):
        await db.delete(memory)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
