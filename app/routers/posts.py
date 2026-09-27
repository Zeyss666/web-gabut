import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..services.publisher import publish_post, utcnow

router = APIRouter(prefix="/api/posts", tags=["posts"])
settings = get_settings()

ALLOWED_PLATFORMS = {"instagram", "facebook", "tiktok"}


def _save_upload(file: UploadFile) -> str:
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".mp4"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(settings.upload_dir, name)
    with open(path, "wb") as f:
        f.write(file.file.read())
    return path


def _parse_tags(tags: str) -> list[str]:
    return [t.strip() for t in tags.split(",") if t.strip()]


def _parse_schedule(s: str):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Format schedule_time tidak valid (gunakan ISO-8601).")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_account(db: Session, user: models.User, account_id: int, platform: str) -> models.PlatformAccount:
    acc = db.query(models.PlatformAccount).filter(
        models.PlatformAccount.id == account_id,
        models.PlatformAccount.user_id == user.id,
    ).first()
    if not acc:
        raise HTTPException(404, "Akun platform tidak ditemukan.")
    if acc.platform != platform:
        raise HTTPException(400, "Platform akun tidak cocok dengan pilihan platform.")
    return acc


def _create_post(db, user, platform, account_id, media_type, caption, tags, product_link, schedule_time, save_as_draft, path):
    _get_account(db, user, account_id, platform)
    if schedule_time and save_as_draft:
        raise HTTPException(400, "Pilih salah satu: simpan draft ATAU jadwalkan.")

    if save_as_draft:
        status, sched = "draft", None
    elif schedule_time:
        status, sched = "scheduled", schedule_time
    else:
        status, sched = "scheduled", utcnow()

    post = models.Post(
        user_id=user.id, platform=platform, account_id=account_id,
        media_type=media_type, video_path=path, caption=caption or None,
        tags=tags, product_link=product_link or None,
        status=status, scheduled_at=sched,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.post("", response_model=schemas.PostOut)
def create_post(
    platform: str = Form(...),
    account_id: int = Form(...),
    video: UploadFile = File(...),
    media_type: str = Form("post"),
    caption: str = Form(""),
    tags: str = Form(""),
    product_link: str = Form(""),
    schedule_time: str = Form(""),
    save_as_draft: bool = Form(False),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(400, "Platform tidak valid.")
    path = _save_upload(video)
    sched = _parse_schedule(schedule_time)
    post = _create_post(
        db, user, platform, account_id, media_type, caption,
        _parse_tags(tags), product_link, sched, save_as_draft, path,
    )
    if not save_as_draft and not schedule_time:
        publish_post(post.id)
        db.refresh(post)
    return post


@router.post("/bulk", response_model=list[schemas.PostOut])
def bulk_create(
    platform: str = Form(...),
    account_id: int = Form(...),
    files: list[UploadFile] = File(...),
    media_type: str = Form("post"),
    caption: str = Form(""),
    tags: str = Form(""),
    product_link: str = Form(""),
    schedule_time: str = Form(""),
    save_as_draft: bool = Form(False),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(400, "Platform tidak valid.")
    sched = _parse_schedule(schedule_time)
    created = []
    for f in files:
        path = _save_upload(f)
        post = _create_post(
            db, user, platform, account_id, media_type, caption,
            _parse_tags(tags), product_link, sched, save_as_draft, path,
        )
        created.append(post)
    return created


@router.get("", response_model=list[schemas.PostOut])
def list_posts(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(models.Post)
        .filter(models.Post.user_id == user.id)
        .order_by(models.Post.created_at.desc())
        .all()
    )


@router.post("/{post_id}/publish", response_model=schemas.PostOut)
def publish_now(post_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = db.query(models.Post).filter(
        models.Post.id == post_id, models.Post.user_id == user.id
    ).first()
    if not post:
        raise HTTPException(404, "Post tidak ditemukan.")
    if post.status == "published":
        return post
    if not post.video_path:
        raise HTTPException(400, "Post tidak punya file video.")
    post.status = "scheduled"
    post.scheduled_at = utcnow()
    db.commit()
    publish_post(post.id)
    db.refresh(post)
    return post


@router.delete("/{post_id}")
def delete_post(post_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = db.query(models.Post).filter(
        models.Post.id == post_id, models.Post.user_id == user.id
    ).first()
    if not post:
        raise HTTPException(404, "Post tidak ditemukan.")
    if post.video_path and os.path.exists(post.video_path):
        try:
            os.remove(post.video_path)
        except OSError:
            pass
    db.delete(post)
    db.commit()
    return {"ok": True}
