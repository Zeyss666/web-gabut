from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services import meta_service, tiktok_service

router = APIRouter(prefix="/api/posts", tags=["analytics"])


@router.get("/{post_id}/analytics", response_model=schemas.AnalyticsOut)
def get_analytics(post_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = db.query(models.Post).filter(
        models.Post.id == post_id, models.Post.user_id == user.id
    ).first()
    if not post:
        raise HTTPException(404, "Post tidak ditemukan.")
    if not post.platform_post_id:
        raise HTTPException(400, "Post belum dipublikasikan (tidak ada platform_post_id).")

    account = db.get(models.PlatformAccount, post.account_id)
    if not account:
        raise HTTPException(404, "Akun platform untuk post ini sudah diputus.")

    likes = comments = views = reach = shares = None
    comments_list: list[dict] = []
    raw: dict = {}

    if post.platform == "instagram":
        ins = meta_service.get_media_insights(post.platform_post_id, account.access_token)
        raw = ins
        likes = ins.get("likes")
        comments = ins.get("comments")
        views = ins.get("plays")
        reach = ins.get("reach")
        shares = ins.get("shares")
        comments_list = meta_service.get_media_comments(post.platform_post_id, account.access_token)
    elif post.platform == "facebook":
        ins = meta_service.get_page_video_insights(post.platform_post_id, account.access_token)
        raw = ins
        views = ins.get("total_video_views")
        comments = ins.get("total_video_comments")
        likes = ins.get("total_video_reactions")
        comments_list = meta_service.get_media_comments(post.platform_post_id, account.access_token)
    elif post.platform == "tiktok":
        st = tiktok_service.get_post_status(account.access_token, post.platform_post_id)
        raw = st

    return schemas.AnalyticsOut(
        platform=post.platform,
        post_id=post.id,
        platform_post_id=post.platform_post_id,
        likes=likes,
        comments=comments,
        views=views,
        reach=reach,
        shares=shares,
        comments_list=comments_list,
        raw=raw,
    )
