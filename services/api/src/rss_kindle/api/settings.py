from __future__ import annotations

from fastapi import APIRouter, Request

from rss_kindle.models import AppSettings
from rss_kindle.services.settings_store import get_app_settings, save_app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def read_settings(request: Request) -> AppSettings:
    return await get_app_settings(request.app.state.db)


@router.put("", response_model=AppSettings)
async def write_settings(payload: AppSettings, request: Request) -> AppSettings:
    db = request.app.state.db
    await save_app_settings(db, payload)
    return await get_app_settings(db)
