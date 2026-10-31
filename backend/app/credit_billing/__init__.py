"""Transactional server-side credits. Every public mutation locks the account first."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.base import utcnow
from app.models import CreativePolicy, CreditAccount, CreditEntry


async def insert_once(db, model, values, keys):
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    await db.execute(insert(model).values(**values).on_conflict_do_nothing(index_elements=keys))


async def policy(db, settings):
    await insert_once(
        db,
        CreativePolicy,
        {
            "id": 1,
            "image_cost": settings.creative_image_cost,
            "video_cost_per_second": settings.creative_video_cost_per_second,
            "monthly_allowance": settings.creative_monthly_allowance,
        },
        ["id"],
    )
    return await db.get(CreativePolicy, 1, populate_existing=True)


async def lock_account(db, user_id, settings):
    rules = await policy(db, settings)
    await insert_once(
        db,
        CreditAccount,
        {
            "user_id": user_id,
            "balance": 0,
            "reserved": 0,
            "consumed": 0,
            "allowance_month": "",
        },
        ["user_id"],
    )
    # A real UPDATE obtains a row lock on PostgreSQL and a write lock on SQLite.
    await db.execute(
        update(CreditAccount).where(CreditAccount.user_id == user_id).values(balance=CreditAccount.balance)
    )
    account = await db.get(CreditAccount, user_id, populate_existing=True)
    month = utcnow().strftime("%Y-%m")
    if account.allowance_month != month:
        allowance = account.monthly_allowance if account.monthly_allowance is not None else rules.monthly_allowance
        account.allowance_month = month
        account.balance += allowance
        db.add(
            CreditEntry(
                user_id=user_id,
                event_key=f"allowance:{month}",
                kind="monthly_allowance",
                amount=allowance,
            )
        )
        await db.flush()
    return account, rules


def reserve(db, account, job):
    if account.balance < job.cost:
        raise HTTPException(402, "Insufficient creative credits")
    account.balance -= job.cost
    account.reserved += job.cost
    db.add(
        CreditEntry(
            user_id=account.user_id, event_key=f"reserve:{job.id}", kind=f"{job.kind}_reserve", amount=-job.cost
        )
    )


def settle(db, account, job, success):
    account.reserved -= job.cost
    if success:
        account.consumed += job.cost
    else:
        account.balance += job.cost
    db.add(
        CreditEntry(
            user_id=account.user_id,
            event_key=f"settle:{job.id}",
            kind=f"{job.kind}_{'consumed' if success else 'refund'}",
            amount=job.cost,
        )
    )


async def grant(db, user_id, amount, key, settings):
    account, _ = await lock_account(db, user_id, settings)
    event = f"admin:{key}"
    existing = await db.scalar(
        select(CreditEntry).where(CreditEntry.user_id == user_id, CreditEntry.event_key == event)
    )
    if existing:
        if existing.amount != amount:
            raise HTTPException(409, "Credit grant key was already used with a different amount")
        return account
    account.balance += amount
    db.add(CreditEntry(id=uuid.uuid4(), user_id=user_id, event_key=event, kind="admin_grant", amount=amount))
    return account
