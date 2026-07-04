from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request, Response, status

from rss_books.models import Group, GroupCreate, GroupUpdate

router = APIRouter(prefix="/api/groups", tags=["groups"])

GROUP_COLUMNS = "id, name, position"


@router.get("", response_model=list[Group])
async def list_groups(request: Request) -> list[Group]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {GROUP_COLUMNS} FROM groups ORDER BY position ASC, id ASC"
        )
        rows = await cur.fetchall()
    return [Group.model_validate(dict(r)) for r in rows]


@router.post("", response_model=Group, status_code=status.HTTP_201_CREATED)
async def create_group(payload: GroupCreate, request: Request) -> Group:
    db = request.app.state.db
    try:
        async with db.connect() as conn:
            cur = await conn.execute(
                "INSERT INTO groups (name, position) VALUES "
                "(?, (SELECT COALESCE(MAX(position), 0) + 1 FROM groups))",
                (payload.name,),
            )
            group_id = cur.lastrowid
            await conn.commit()
            cur = await conn.execute(
                f"SELECT {GROUP_COLUMNS} FROM groups WHERE id = ?", (group_id,)
            )
            row = await cur.fetchone()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="a group with this name exists") from e
    if row is None:
        raise RuntimeError(f"group {group_id} not found after insert")
    return Group.model_validate(dict(row))


@router.patch("/{group_id}", response_model=Group)
async def update_group(group_id: int, payload: GroupUpdate, request: Request) -> Group:
    db = request.app.state.db
    fields = payload.model_dump(exclude_none=True)
    try:
        async with db.connect() as conn:
            if fields:
                sets = ", ".join(f"{name} = ?" for name in fields)
                cur = await conn.execute(
                    f"UPDATE groups SET {sets} WHERE id = ?",  # noqa: S608 (keys from the model)
                    (*fields.values(), group_id),
                )
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="group not found")
                await conn.commit()
            cur = await conn.execute(
                f"SELECT {GROUP_COLUMNS} FROM groups WHERE id = ?", (group_id,)
            )
            row = await cur.fetchone()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="a group with this name exists") from e
    if row is None:
        raise HTTPException(status_code=404, detail="group not found")
    return Group.model_validate(dict(row))


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: int, request: Request) -> Response:
    # Member feeds keep their subscriptions; the FK sets their group_id NULL.
    db = request.app.state.db
    async with db.connect() as conn:
        await conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        await conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
