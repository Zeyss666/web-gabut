"""Integrasi TikTok (Login Kit OAuth + Content Posting API).

Catatan penting (lihat README):
- Content Posting API TIDAK self-service: butuh approval TikTok untuk scope
  `video.publish`. Tanpa approval, content yang di-post akan "private".
- Fitur Story, tag orang, dan link dagangan (TikTok Shop) TIDAK didukung oleh
  Content Posting API. Mention (@user) & hashtag bisa lewat teks caption.
"""
import os

import httpx

from ..config import get_settings

settings = get_settings()

TIKTOK_API = "https://open.tiktokapis.com"
TIKTOK_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"

TIKTOK_SCOPES = "user.info.basic,video.publish"


def _err(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        data = {"message": resp.text}
    err = data.get("error", data)
    if isinstance(err, dict):
        msg = err.get("message") or err.get("description") or str(err)
    else:
        msg = str(err)
    return f"TikTok API error ({resp.status_code}): {msg}"


def build_authorize_url(redirect_uri: str, state: str) -> str:
    return (
        f"{TIKTOK_AUTHORIZE_URL}?client_key={settings.tiktok_client_key}"
        f"&response_type=code"
        f"&scope={TIKTOK_SCOPES}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )


def exchange_code(code: str, redirect_uri: str) -> dict:
    resp = httpx.post(
        f"{TIKTOK_API}/v2/oauth/token/",
        data={
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError("Tidak menerima access_token dari TikTok.")
    return data


def refresh_access_token(refresh_token: str) -> dict:
    resp = httpx.post(
        f"{TIKTOK_API}/v2/oauth/token/",
        data={
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json()


def query_creator_info(token: str) -> dict:
    resp = httpx.post(
        f"{TIKTOK_API}/v2/post/publish/creator_info/query/",
        headers={"Authorization": f"Bearer {token}"},
        json={},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json().get("data", {})


def publish_video(
    token: str,
    source: str,
    title: str,
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    disable_duet: bool = False,
    disable_comment: bool = False,
    disable_stitch: bool = False,
) -> str:
    """Post video ke TikTok. Mengembalikan `publish_id`."""
    post_info = {
        "title": title,
        "privacy_level": privacy_level,
        "disable_duet": disable_duet,
        "disable_comment": disable_comment,
        "disable_stitch": disable_stitch,
        "video_cover_timestamp_ms": 1000,
    }

    if source.startswith("http://") or source.startswith("https://"):
        source_info = {"source": "PULL_FROM_URL", "video_url": source}
        resp = httpx.post(
            f"{TIKTOK_API}/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json={"post_info": post_info, "source_info": source_info},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(_err(resp))
        return resp.json()["data"]["publish_id"]

    # FILE_UPLOAD
    if not os.path.exists(source):
        raise RuntimeError(f"File video tidak ditemukan: {source}")
    size = os.path.getsize(source)
    source_info = {
        "source": "FILE_UPLOAD",
        "video_size": size,
        "chunk_size": size,
        "total_chunk_count": 1,
    }
    resp = httpx.post(
        f"{TIKTOK_API}/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"post_info": post_info, "source_info": source_info},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    data = resp.json()["data"]
    publish_id = data["publish_id"]
    upload_url = data["upload_url"]

    with open(source, "rb") as f:
        content = f.read()

    up = httpx.put(
        upload_url,
        content=content,
        headers={
            "Content-Range": f"bytes 0-{size - 1}/{size}",
            "Content-Type": "video/mp4",
        },
        timeout=600,
    )
    if up.status_code not in (200, 201):
        raise RuntimeError(_err(up))
    return publish_id


def get_post_status(token: str, publish_id: str) -> dict:
    resp = httpx.post(
        f"{TIKTOK_API}/v2/post/publish/status/fetch/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"publish_id": publish_id},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(_err(resp))
    return resp.json().get("data", {})
