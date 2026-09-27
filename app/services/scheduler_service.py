"""Background scheduler: otomatis posting konten sesuai jadwal user."""
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from ..database import SessionLocal
from ..models import Post
from .publisher import publish_post

scheduler = BackgroundScheduler(timezone="UTC")


def _tick() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due = (
            db.query(Post)
            .filter(Post.status == "scheduled", Post.scheduled_at.isnot(None), Post.scheduled_at <= now)
            .all()
        )
        ids = [p.id for p in due]
    finally:
        db.close()

    for pid in ids:
        publish_post(pid)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.add_job(_tick, "interval", seconds=30, id="publish_tick")
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
