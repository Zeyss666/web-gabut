"""Menerbitkan satu Post ke platform target (dipakai router & scheduler)."""
from datetime import datetime, timedelta, timezone

from ..database import SessionLocal
from ..models import PlatformAccount, Post
from . import meta_service, tiktok_service


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _with_link(caption: str | None, product_link: str | None) -> str | None:
    parts = []
    if caption:
        parts.append(caption)
    if product_link:
        parts.append(f"Produk: {product_link}")
    return "\n\n".join(parts) if parts else None


def _refresh_if_needed(account: PlatformAccount) -> PlatformAccount:
    """Refresh token TikTok bila hampir/ sudah kedaluwarsa."""
    if account.platform == "tiktok" and account.refresh_token:
        exp = account.token_expires_at
        if exp is None or exp <= utcnow():
            new = tiktok_service.refresh_access_token(account.refresh_token)
            account.access_token = new["access_token"]
            account.refresh_token = new.get("refresh_token") or account.refresh_token
            account.token_expires_at = utcnow() + timedelta(seconds=int(new.get("expires_in", 86400)))
    return account


def publish_post(post_id: int) -> None:
    """Publikasikan post (idempotent, thread-safe: buka session sendiri)."""
    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
        if not post:
            return
        account = db.get(PlatformAccount, post.account_id)
        if not account:
            post.status = "failed"
            post.error_message = "Akun platform tidak ditemukan."
            db.commit()
            return

        post.status = "publishing"
        db.commit()

        try:
            account = _refresh_if_needed(account)
            caption = _with_link(post.caption, post.product_link)

            if post.platform == "instagram":
                result_id = meta_service.publish_instagram(
                    ig_user_id=account.extra.get("ig_user_id") or account.platform_user_id,
                    token=account.access_token,
                    media_type=post.media_type,
                    source=post.video_path,
                    caption=caption,
                    tags=post.tags or [],
                )
            elif post.platform == "facebook":
                result_id = meta_service.publish_facebook_page(
                    page_id=account.platform_user_id,
                    token=account.access_token,
                    source=post.video_path,
                    caption=caption,
                    schedule_time=post.scheduled_at,
                )
            elif post.platform == "tiktok":
                result_id = tiktok_service.publish_video(
                    token=account.access_token,
                    source=post.video_path,
                    title=post.caption or "",
                    privacy_level=account.extra.get("privacy_level", "PUBLIC_TO_EVERYONE"),
                )
            else:
                raise RuntimeError(f"Platform tidak didukung: {post.platform}")

            post.platform_post_id = result_id
            post.status = "published"
            post.published_at = utcnow()
            post.error_message = None
            db.commit()
        except Exception as e:  # noqa: BLE001
            post.status = "failed"
            post.error_message = str(e)
            db.commit()
    finally:
        db.close()
