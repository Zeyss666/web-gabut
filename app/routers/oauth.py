from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..security import decode_oauth_state, make_oauth_state
from ..services import meta_service, tiktok_service

router = APIRouter(prefix="/api/oauth", tags=["oauth"])
settings = get_settings()

META_REDIRECT = f"{settings.base_url}/api/oauth/meta/callback"
TIKTOK_REDIRECT = f"{settings.base_url}/api/oauth/tiktok/callback"


@router.get("/meta/authorize")
def meta_authorize(user: models.User = Depends(get_current_user)):
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise HTTPException(400, "Meta App ID/Secret belum diisi di .env")
    state = make_oauth_state(user.id, "meta")
    return {"authorize_url": meta_service.build_authorize_url(META_REDIRECT, state)}


@router.get("/tiktok/authorize")
def tiktok_authorize(user: models.User = Depends(get_current_user)):
    if not settings.tiktok_client_key or not settings.tiktok_client_secret:
        raise HTTPException(400, "TikTok client key/secret belum diisi di .env")
    state = make_oauth_state(user.id, "tiktok")
    return {"authorize_url": tiktok_service.build_authorize_url(TIKTOK_REDIRECT, state)}


@router.get("/meta/callback")
def meta_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        payload = decode_oauth_state(state)
    except jwt.PyJWTError:
        raise HTTPException(400, "State OAuth tidak valid.")
    if payload.get("platform") != "meta":
        raise HTTPException(400, "State platform tidak cocok.")
    user_id = int(payload["sub"])

    short_token = meta_service.exchange_code(code, META_REDIRECT)["access_token"]
    long_token = meta_service.exchange_long_lived_token(short_token)
    pages = meta_service.get_pages(long_token)

    count = 0
    for page in pages:
        page_token = page.get("access_token")
        page_id = page.get("id")
        page_name = page.get("name")
        if not page_token or not page_id:
            continue

        fb = db.query(models.PlatformAccount).filter(
            models.PlatformAccount.user_id == user_id,
            models.PlatformAccount.platform == "facebook",
            models.PlatformAccount.platform_user_id == page_id,
        ).first()
        if fb:
            fb.access_token = page_token
            fb.account_name = page_name
        else:
            db.add(models.PlatformAccount(
                user_id=user_id, platform="facebook", account_name=page_name,
                platform_user_id=page_id, access_token=page_token, extra={},
            ))
            count += 1

        ig = page.get("instagram_business_account")
        if ig:
            ig_id = ig.get("id")
            ig_acc = db.query(models.PlatformAccount).filter(
                models.PlatformAccount.user_id == user_id,
                models.PlatformAccount.platform == "instagram",
                models.PlatformAccount.platform_user_id == ig_id,
            ).first()
            if ig_acc:
                ig_acc.access_token = page_token
            else:
                db.add(models.PlatformAccount(
                    user_id=user_id, platform="instagram",
                    account_name=ig.get("username") or ig.get("name"),
                    platform_user_id=ig_id, access_token=page_token,
                    extra={"ig_user_id": ig_id},
                ))
                count += 1

    db.commit()
    return RedirectResponse(url=f"{settings.base_url}/?connected=meta&count={count}")


@router.get("/tiktok/callback")
def tiktok_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        payload = decode_oauth_state(state)
    except jwt.PyJWTError:
        raise HTTPException(400, "State OAuth tidak valid.")
    if payload.get("platform") != "tiktok":
        raise HTTPException(400, "State platform tidak cocok.")
    user_id = int(payload["sub"])

    tok = tiktok_service.exchange_code(code, TIKTOK_REDIRECT)
    info = {}
    try:
        info = tiktok_service.query_creator_info(tok["access_token"])
    except Exception:
        pass

    open_id = tok.get("open_id")
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 86400)))
    acc = db.query(models.PlatformAccount).filter(
        models.PlatformAccount.user_id == user_id,
        models.PlatformAccount.platform == "tiktok",
        models.PlatformAccount.platform_user_id == open_id,
    ).first()
    if acc:
        acc.access_token = tok["access_token"]
        acc.refresh_token = tok.get("refresh_token") or acc.refresh_token
        acc.token_expires_at = expires_at
    else:
        db.add(models.PlatformAccount(
            user_id=user_id, platform="tiktok",
            account_name=info.get("creator_username") or info.get("creator_nickname") or "TikTok",
            platform_user_id=open_id, access_token=tok["access_token"],
            refresh_token=tok.get("refresh_token"), token_expires_at=expires_at,
            extra={"privacy_level": "PUBLIC_TO_EVERYONE"},
        ))
    db.commit()
    return RedirectResponse(url=f"{settings.base_url}/?connected=tiktok")
