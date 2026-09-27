# 📤 SocialPoster

Aplikasi web untuk **mengupload & menjadwalkan video** ke **TikTok, Instagram, dan Facebook** dari satu dashboard, lengkap dengan **draft**, **bulk upload (banyak video sekaligus)**, **jadwal auto-post**, dan **monitoring (like/views/comment)**.

> Stack: Python 3.11+ · FastAPI · SQLAlchemy (SQLite) · APScheduler · frontend HTML/JS (tanpa Node).

---

## ⚠️ PENTING — Realita soal API key (baca dulu!)

Kamu **tidak bisa "mendapatkan" API key dari siapa pun** — termasuk saya. API key/App ID/App Secret itu **dibuat dari akun developer milikmu sendiri** dan harus kamu daftarkan + verifikasi. Saya sudah menyiapkan seluruh kode integrasinya; kamu tinggal menempelkan kredensialnya ke file `.env`.

| Platform | Bisa posting via API? | Syarat |
|---|---|---|
| **Instagram** (Reels, Story, caption, tag orang) | ✅ Ya | Akun **Business/Creator** yang terhubung ke **Facebook Page** |
| **Facebook** (video ke Page, jadwal) | ✅ Ya | Facebook Page + hak akses |
| **TikTok** (video biasa) | ⚠️ Terbatas | **Content Posting API butuh approval TikTok** (bukan self-service). Tanpa approval, posting jadi *private* |
| TikTok Story / tag orang / link dagangan (Shop) | ❌ Tidak didukung API resmi | Tidak ada endpoint publik |

---

## 1. Cara menjalankan

```powershell
# dari folder e:\webper1
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt

# salin contoh konfigurasi
Copy-Item .env.example .env

# jalankan
py run.py
```

Buka **http://localhost:8000** → register akun → hubungkan platform → mulai posting.

---

## 2. Mendapatkan kredensial (yang harus KAMU lakukan)

### Meta (Instagram + Facebook)
1. Buat app di https://developers.facebook.com/apps → ambil **App ID** & **App Secret**.
2. Tambahkan produk **Facebook Login** (untuk Business) dan aktifkan **Instagram Graph API**.
3. Di pengaturan Facebook Login:
   - Tambah **Valid OAuth Redirect URI**:
     - `http://localhost:8000/api/oauth/meta/callback`
   - Tambahkan scopes: `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `business_management`.
4. Isi `META_APP_ID` & `META_APP_SECRET` di `.env`.
5. **Akun Instagram harus Business/Creator** dan terhubung ke Facebook Page (Setting → Linked accounts).

### TikTok
1. Buat app di https://developers.tiktok.com/ → ambil **Client Key** & **Client Secret**.
2. Tambahkan produk **Content Posting API** → aktifkan **Direct Post**.
3. Minta **approval scope `video.publish`** (ini yang menentukan bisa posting publik atau hanya private).
4. Tambah redirect URI: `http://localhost:8000/api/oauth/tiktok/callback`.
5. Isi `TIKTOK_CLIENT_KEY` & `TIKTOK_CLIENT_SECRET` di `.env`.

---

## 3. Fitur

- 🔐 Register/login (JWT).
- 🔗 Connect Instagram, Facebook, TikTok (OAuth).
- 🎬 Upload video: pilih format **Reels / Story / Post / Foto**.
- ✍️ Caption, **tag orang** (IG), link produk (ditambahkan ke caption).
- 💾 **Draft** atau **Post sekarang**.
- 📦 **Bulk upload** banyak video sekaligus.
- ⏰ **Jadwal auto-post** — background scheduler (APScheduler) mengecek tiap 30 detik.
- 📊 **Monitoring** likes / views / comments / reach (IG & FB via Graph API; TikTok mengembalikan status publish karena API tidak menyediakan metrik publik).

---

## 4. Struktur

```
app/
  main.py             # FastAPI app + static + scheduler
  config.py           # baca .env
  models.py           # User, PlatformAccount, Post
  routers/            # auth, oauth, accounts, posts, analytics
  services/           # meta_service, tiktok_service, publisher, scheduler
  static/             # frontend (index.html, app.js, styles.css)
uploads/              # video tersimpan (dibuat otomatis)
```

---

## 5. Catatan teknis

- **Sumber video**: untuk IG, cara paling andal adalah **URL publik** (`video_url`). Upload file lokal memakai *resumable upload* (`upload_type=resumable` + `rupload.facebook.com`). Untuk Facebook dipakai upload `graph-video` (mendukung file lokal + `scheduled_publish_time`). Untuk TikTok dipakai `FILE_UPLOAD`/`PULL_FROM_URL`.
- Token disimpan di database SQLite (`socialposter.db`). Untuk produksi, pindahkan ke Postgres + enkripsi token.
- Ganti `SECRET_KEY` di `.env` dengan string acak panjang.
