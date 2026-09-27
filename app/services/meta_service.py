"""Integrasi Meta Graph API (Instagram + Facebook).

Catatan penting (lihat README):
- Instagram: butuh akun Business/Creator yang terhubung ke Facebook Page.
- Sumber video: gunakan URL publik (paling andal) ATAU upload lokal via
  resumable upload (`upload_type=resumable` + rupload.facebook.com).
- Fitur "story" didukung (media_type=STORIES), "tag orang" via `user_tags`.
- Product tagging butuh katalog produk (product_id) — untuk saat ini link produk
  otomatis ditambahkan ke caption.
"""
import json
import os

import httpx

from ..config import get_settings

settings = get_settings()

# Versi API Meta. Naikkan bila Meta menonaktifkan versi lama.
META_API_VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{META_API_VERSION}"
GRAPH_VIDEO = f"https://graph-video.facebook.com/{META_API_VERSION}"
RUPLOAD = "https://rupload.facebook.com"

META_AUTHORIZE_URL = f"https://www.facebook.com/{META_API_VERSION}/dialog/oauth"

META_SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_comments",
    "instagram_manage_insights",
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "business_management",
]

# media_type dari aplikasi -> media_type Meta
MEDIA_TYPE_MAP = {
    "reel": "REELS",
    "story": "STORIES",
    "video": "VIDEO",
    "post": "VIDEO",
    "photo": "IMAGE",
}


def _err(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        data = {"message": resp.text}
    err = data.get("error", data)
    if isinstance(err, dict):
        msg = err.get("message") or err.get("error_user_msg") or json.dumps(err)
    else:
        msg = str(err)
    return f"Meta API error ({resp.status_code}): {msg}"


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


# --------------------------------------------------------------------------
# OAuth / token
# --------------------------------------------------------------------------
def build_authorize_url(redirect_uri: str, state: str) -> str:
    return (
        f"{META_AUTHORIZE_URL}?client_id={settings.meta_app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
        f"&scope={','.join(META_SCOPES)}"
        f"&response_type=code"
    )


def exchange_code(code: str, redirect_uri: str) -> dict:
    resp = httpx.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError("Tidak menerima access_token dari Meta.")
    return data


def exchange_long_lived_token(short_lived_token: str) -> str:
    resp = httpx.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "fb_exchange_token": short_lived_token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json()["access_token"]


def get_me(token: str) -> dict:
    resp = httpx.get(
        f"{GRAPH}/me",
        params={"fields": "id,name", "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json()


def get_pages(token: str) -> list[dict]:
    """Ambil halaman FB + akun Instagram bisnis yang terhubung."""
    resp = httpx.get(
        f"{GRAPH}/me/accounts",
        params={
            "fields": "id,name,access_token,instagram_business_account{id,username,name}",
            "access_token": token,
            "limit": 100,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json().get("data", [])


# --------------------------------------------------------------------------
# Publishing Instagram
# --------------------------------------------------------------------------
def publish_instagram(
    ig_user_id: str,
    token: str,
    media_type: str,
    source: str,
    caption: str | None = None,
    tags: list[str] | None = None,
    share_to_feed: bool = True,
) -> str:
    """Posting Reels/Story/feed video (atau foto) ke akun Instagram bisnis.

    `source` berupa URL publik ATAU path file lokal. Mengembalikan media ID.
    """
    mt = MEDIA_TYPE_MAP.get(media_type, "VIDEO")
    data = {"media_type": mt, "access_token": token}

    if caption:
        data["caption"] = caption
    if mt == "REELS" and share_to_feed:
        data["share_to_feed"] = "true"
    if tags:
        data["user_tags"] = json.dumps(
            [{"username": t, "x": 0.5, "y": 0.5} for t in tags]
        )

    if _is_url(source):
        key = "image_url" if mt == "IMAGE" else "video_url"
        data[key] = source
    else:
        data["upload_type"] = "resumable"

    resp = httpx.post(f"{GRAPH}/{ig_user_id}/media", data=data, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    container_id = resp.json().get("id")
    if not container_id:
        raise RuntimeError("Meta tidak mengembalikan container ID.")

    if not _is_url(source):
        _upload_resumable_video(container_id, token, source)

    pub = httpx.post(
        f"{GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=60,
    )
    if pub.status_code != 200:
        raise RuntimeError(_err(pub))
    return pub.json().get("id")


def _upload_resumable_video(container_id: str, token: str, file_path: str) -> None:
    """Upload video lokal ke sesi resumable Instagram (rupload.facebook.com)."""
    if not os.path.exists(file_path):
        raise RuntimeError(f"File video tidak ditemukan: {file_path}")
    size = os.path.getsize(file_path)

    sid = container_id
    try:
        r = httpx.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "upload_session_id,status_code", "access_token": token},
            timeout=30,
        )
        if r.status_code == 200:
            sid = r.json().get("upload_session_id") or container_id
    except Exception:
        pass

    with open(file_path, "rb") as f:
        content = f.read()

    upload_url = f"{RUPLOAD}/video-upload/{META_API_VERSION}/{sid}"
    headers = {
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(size),
        "Content-Type": "video/mp4",
    }
    up = httpx.post(upload_url, content=content, headers=headers, timeout=600)
    if up.status_code not in (200, 201):
        raise RuntimeError(_err(up))


# --------------------------------------------------------------------------
# Publishing Facebook Page (video)
# --------------------------------------------------------------------------
def publish_facebook_page(
    page_id: str,
    token: str,
    source: str,
    caption: str | None = None,
    schedule_time=None,
) -> str:
    """Upload video ke Facebook Page. Mendukung jadwal (scheduled_publish_time)."""
    if _is_url(source):
        data = {
            "file_url": source,
            "description": caption or "",
            "access_token": token,
        }
        if schedule_time:
            data["scheduled_publish_time"] = str(int(schedule_time.timestamp()))
            data["published"] = "false"
        resp = httpx.post(f"{GRAPH}/{page_id}/videos", data=data, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(_err(resp))
        return resp.json().get("id")

    if not os.path.exists(source):
        raise RuntimeError(f"File video tidak ditemukan: {source}")
    size = os.path.getsize(source)
    with open(source, "rb") as f:
        content = f.read()

    params = {"access_token": token}
    if caption:
        params["description"] = caption
    if schedule_time:
        params["scheduled_publish_time"] = str(int(schedule_time.timestamp()))
        params["published"] = "false"

    headers = {
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(size),
        "Content-Type": "video/mp4",
    }
    resp = httpx.post(
        f"{GRAPH_VIDEO}/{page_id}/videos",
        params=params,
        content=content,
        headers=headers,
        timeout=600,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json().get("id")


# --------------------------------------------------------------------------
# Insights / monitoring (like, views, comment)
# --------------------------------------------------------------------------
def get_media_insights(media_id: str, token: str) -> dict:
    metrics = "likes,comments,plays,reach,shares,saved,total_interactions"
    resp = httpx.get(
        f"{GRAPH}/{media_id}/insights",
        params={"metric": metrics, "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    out = {}
    for row in resp.json().get("data", []):
        name = row.get("name")
        values = row.get("values") or []
        if values and "value" in values[0]:
            out[name] = values[0]["value"]
    return out


def get_media_comments(media_id: str, token: str) -> list[dict]:
    resp = httpx.get(
        f"{GRAPH}/{media_id}/comments",
        params={
            "fields": "id,text,username,timestamp,like_count",
            "access_token": token,
            "limit": 100,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json().get("data", [])


def get_page_video_insights(video_id: str, token: str) -> dict:
    """Insight dasar video Facebook Page."""
    resp = httpx.get(
        f"{GRAPH}/{video_id}/video_insights",
        params={
            "metric": "total_video_views,total_video_views_unique,total_video_comments,total_video_reactions",
            "access_token": token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    out = {}
    for row in resp.json().get("data", []):
        name = row.get("name")
        values = row.get("values") or []
        if values and "value" in values[0]:
            out[name] = values[0]["value"]
    return out


