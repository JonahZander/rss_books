from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rss_books.models import AppSettings
from rss_books.services.emailer import EmailError, send_test_email
from rss_books.services.settings_store import get_app_settings, save_app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class TestEmailRequest(BaseModel):
    to: list[str] | None = None


@router.get("", response_model=AppSettings)
async def read_settings(request: Request) -> AppSettings:
    return await get_app_settings(request.app.state.db)


@router.put("", response_model=AppSettings)
async def write_settings(payload: AppSettings, request: Request) -> AppSettings:
    if payload.default_profile and payload.default_profile not in {
        p.name for p in payload.profiles
    }:
        raise HTTPException(
            status_code=400,
            detail=f"unknown default profile: {payload.default_profile!r}",
        )
    db = request.app.state.db
    await save_app_settings(db, payload)
    return await get_app_settings(db)


@router.post("/test-email")
async def test_email(payload: TestEmailRequest, request: Request) -> dict[str, list[str]]:
    app_settings = await get_app_settings(request.app.state.db)
    try:
        recipients = await send_test_email(app_settings, payload.to)
    except EmailError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"sent_to": recipients}
