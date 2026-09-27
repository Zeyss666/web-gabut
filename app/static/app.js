const $ = (sel) => document.querySelector(sel);

let token = localStorage.getItem("token") || "";
let accounts = [];
let authMode = "login";

// ---------- API helper ----------
async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers["Authorization"] = "Bearer " + token;
  if (opts.body && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error("Sesi berakhir, silakan login."); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Terjadi kesalahan.");
  return data;
}

// ---------- Auth ----------
function showAuth() {
  $("#dashboard").classList.add("hidden");
  $("#authScreen").classList.remove("hidden");
}
function showDashboard() {
  $("#authScreen").classList.add("hidden");
  $("#dashboard").classList.remove("hidden");
}
function logout() {
  token = "";
  localStorage.removeItem("token");
  showAuth();
}

function setAuthMode(mode) {
  authMode = mode;
  $("#authUsername").classList.toggle("hidden", mode !== "register");
  $("#authSubmit").textContent = mode === "login" ? "Login" : "Daftar";
  $("#tabLogin").classList.toggle("active", mode === "login");
  $("#tabRegister").classList.toggle("active", mode === "register");
}

async function onAuthSubmit(e) {
  e.preventDefault();
  $("#authError").classList.add("hidden");
  const email = $("#authEmail").value.trim();
  const password = $("#authPassword").value;
  const username = $("#authUsername").value.trim();
  try {
    const data = await api("/api/auth/" + authMode, {
      method: "POST",
      body: authMode === "login" ? { email, password } : { email, password, username },
    });
    token = data.access_token;
    localStorage.setItem("token", token);
    await bootstrap();
  } catch (err) {
    $("#authError").textContent = err.message;
    $("#authError").classList.remove("hidden");
  }
}

// ---------- Connect accounts ----------
async function connect(platform) {
  try {
    const ep = platform === "meta" ? "/api/oauth/meta/authorize" : "/api/oauth/tiktok/authorize";
    const { authorize_url } = await api(ep);
    window.location.href = authorize_url;
  } catch (err) { alert(err.message); }
}

async function loadAccounts() {
  accounts = await api("/api/accounts");
  renderAccounts();
}

function renderAccounts() {
  const box = $("#accountsList");
  box.innerHTML = "";
  if (!accounts.length) {
    box.innerHTML = '<p class="muted">Belum ada akun terhubung.</p>';
  }
  accounts.forEach((a) => {
    const chip = document.createElement("div");
    chip.className = "account-chip";
    const label = { instagram: "📸", facebook: "👍", tiktok: "🎵" }[a.platform] || "•";
    chip.innerHTML = `${label} ${a.platform} · ${a.account_name || a.platform_user_id || "?"}`;
    const btn = document.createElement("button");
    btn.textContent = "putus";
    btn.onclick = () => disconnect(a.id);
    chip.appendChild(btn);
    box.appendChild(chip);
  });

  const platform = $("#platform").value;
  const opts = ['<option value="">— pilih akun —</option>'];
  accounts.filter((a) => a.platform === platform).forEach((a) => {
    opts.push(`<option value="${a.id}">${a.account_name || a.platform_user_id || a.id}</option>`);
  });
  $("#account").innerHTML = opts.join("");
}

async function disconnect(id) {
  if (!confirm("Putuskan akun ini?")) return;
  await api("/api/accounts/" + id, { method: "DELETE" });
  await loadAccounts();
}

// ---------- Posts ----------
async function loadPosts() {
  const posts = await api("/api/posts");
  const tbody = $("#postsTbody");
  tbody.innerHTML = "";
  posts.forEach((p) => {
    const tr = document.createElement("tr");
    const sched = p.scheduled_at ? new Date(p.scheduled_at + "Z").toLocaleString() : "—";
    const actions = [];
    if (p.status !== "published") {
      actions.push(`<button onclick="publishNow(${p.id})">Posting</button>`);
    }
    actions.push(`<button onclick="viewAnalytics(${p.id})">Monitoring</button>`);
    if (p.status === "draft" || p.status === "failed") {
      actions.push(`<button onclick="deletePost(${p.id})">Hapus</button>`);
    }
    const cap = (p.caption || "").slice(0, 40);
    tr.innerHTML = `
      <td>${p.platform}</td>
      <td>${p.media_type}</td>
      <td><span class="status ${p.status}">${p.status}</span>${p.error_message ? `<br><span class="muted">${p.error_message.slice(0, 60)}</span>` : ""}</td>
      <td>${cap}</td>
      <td>${sched}</td>
      <td><div class="row-actions">${actions.join("")}</div></td>`;
    tbody.appendChild(tr);
  });
}

async function publishNow(id) {
  await api(`/api/posts/${id}/publish`, { method: "POST" });
  await loadPosts();
}

async function deletePost(id) {
  if (!confirm("Hapus postingan ini?")) return;
  await api(`/api/posts/${id}`, { method: "DELETE" });
  await loadPosts();
}

// ---------- Create / bulk ----------
function collectFields() {
  return {
    platform: $("#platform").value,
    account_id: $("#account").value,
    media_type: $("#mediaType").value,
    caption: $("#caption").value,
    tags: $("#tags").value,
    product_link: $("#productLink").value,
    schedule_time: $("#scheduleTime").value ? new Date($("#scheduleTime").value).toISOString() : "",
    save_as_draft: $("#draftCheck").checked,
  };
}

async function onSubmitPost(e) {
  e.preventDefault();
  const f = collectFields();
  if (!f.account_id) return alert("Pilih akun dulu.");
  if (!$("#videoInput").files.length) return alert("Pilih video untuk diupload.");
  const fd = new FormData();
  Object.entries(f).forEach(([k, v]) => fd.append(k, v));
  fd.append("video", $("#videoInput").files[0]);
  try {
    const p = await api("/api/posts", { method: "POST", body: fd });
    $("#postMsg").textContent = `Postingan dibuat (status: ${p.status}).`;
    $("#postMsg").classList.remove("hidden");
    $("#videoInput").value = "";
    await loadPosts();
  } catch (err) { alert(err.message); }
}

async function onBulkSubmit() {
  const f = collectFields();
  if (!f.account_id) return alert("Pilih akun dulu.");
  const files = $("#bulkFiles").files;
  if (!files.length) return alert("Pilih beberapa video dulu.");
  const fd = new FormData();
  Object.entries(f).forEach(([k, v]) => fd.append(k, v));
  for (const file of files) fd.append("files", file);
  try {
    const posts = await api("/api/posts/bulk", { method: "POST", body: fd });
    $("#postMsg").textContent = `${posts.length} video masuk antrean posting.`;
    $("#postMsg").classList.remove("hidden");
    $("#bulkFiles").value = "";
    await loadPosts();
  } catch (err) { alert(err.message); }
}

// ---------- Analytics ----------
async function viewAnalytics(id) {
  try {
    const a = await api(`/api/posts/${id}/analytics`);
    const fmt = (v) => (v == null ? "—" : v);
    let comments = "";
    (a.comments_list || []).forEach((c) => {
      comments += `<div class="comment"><b>${c.username || "?"}</b>: ${c.text || ""}</div>`;
    });
    $("#analyticsContent").innerHTML = `
      <p class="muted">Platform: <b>${a.platform}</b> · ID: <b>${a.platform_post_id || "—"}</b></p>
      <div class="stat-grid">
        <div class="stat"><div class="num">${fmt(a.likes)}</div><div class="lbl">Likes</div></div>
        <div class="stat"><div class="num">${fmt(a.views)}</div><div class="lbl">Views</div></div>
        <div class="stat"><div class="num">${fmt(a.comments)}</div><div class="lbl">Comments</div></div>
        <div class="stat"><div class="num">${fmt(a.reach)}</div><div class="lbl">Reach</div></div>
        <div class="stat"><div class="num">${fmt(a.shares)}</div><div class="lbl">Shares</div></div>
      </div>
      <h3>Komentar</h3>${comments || '<p class="muted">Tidak ada komentar / tidak didukung.</p>'}`;
    $("#analyticsModal").classList.remove("hidden");
  } catch (err) {
    alert("Monitoring gagal: " + err.message);
  }
}

// ---------- Bootstrap ----------
async function bootstrap() {
  if (!token) { showAuth(); return; }
  showDashboard();
  try {
    const me = await api("/api/auth/me");
    $("#usernameEl").textContent = me.username || me.email;
    await loadAccounts();
    await loadPosts();
  } catch (err) {
    logout();
  }
}

// ---------- Wire events ----------
$("#tabLogin").onclick = () => setAuthMode("login");
$("#tabRegister").onclick = () => setAuthMode("register");
$("#authForm").onsubmit = onAuthSubmit;
$("#logoutBtn").onclick = logout;
$("#platform").onchange = renderAccounts;
document.querySelectorAll(".connect-btn").forEach((b) => (b.onclick = () => connect(b.dataset.platform)));
$("#postForm").onsubmit = onSubmitPost;
$("#bulkBtn").onclick = onBulkSubmit;
$("#modalClose").onclick = () => $("#analyticsModal").classList.add("hidden");
$("#analyticsModal").onclick = (e) => { if (e.target.id === "analyticsModal") $("#analyticsModal").classList.add("hidden"); };

// Handle pesan setelah OAuth redirect
const params = new URLSearchParams(location.search);
if (params.get("connected")) {
  $("#connectMsg").textContent = `✅ Berhasil terhubung (${params.get("connected")}).`;
  $("#connectMsg").classList.remove("hidden");
  history.replaceState({}, "", "/");
}

bootstrap();

