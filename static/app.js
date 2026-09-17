"use strict";

const $ = (s, el = document) => el.querySelector(s);
const state = { jobs: {}, current: null, src: "file", file: null, config: null };

const STATUS_LABEL = {
  queued: "Antre", downloading: "Mengunduh", preparing: "Menyiapkan", analyzing: "Analisis AI",
  rendering: "Render", done: "Selesai", error: "Gagal",
};
const LAYOUT_LABEL = { face: "fokus wajah", crop: "crop tengah", blur: "latar blur" };
const RUNNING = new Set(["queued", "downloading", "preparing", "analyzing", "rendering"]);

// ---------- Utilitas ----------
function fmt(t) {
  t = Math.max(0, Number(t) || 0);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = (t % 60).toFixed(1).padStart(4, "0");
  return (h ? `${h}:${String(m).padStart(2, "0")}` : String(m).padStart(2, "0")) + ":" + s;
}
function parseTime(str) {
  const parts = String(str).trim().split(":").map(Number);
  if (parts.some(isNaN)) return NaN;
  return parts.reduce((acc, p) => acc * 60 + p, 0);
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
let toastTimer;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (isError ? " error" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 4000);
}
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ---------- Realtime (WebSocket) ----------
function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  let ping;
  ws.onopen = () => {
    $("#conn").className = "pill on";
    $("#conn").textContent = "● realtime";
    ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 20000);
  };
  ws.onclose = () => {
    $("#conn").className = "pill off";
    $("#conn").textContent = "● offline";
    clearInterval(ping);
    setTimeout(connect, 1500);
  };
  ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
}

function handleEvent(ev) {
  switch (ev.type) {
    case "snapshot":
      state.jobs = Object.fromEntries(ev.jobs.map((j) => [j.id, j]));
      renderJobList();
      if (state.current && state.jobs[state.current]) renderJob();
      else if (state.current) showNew();
      break;
    case "job":
      state.jobs[ev.job.id] = ev.job;
      renderJobList();
      if (ev.job.id === state.current) renderJob();
      break;
    case "progress": {
      const job = state.jobs[ev.job_id];
      if (!job) return;
      if (ev.clip_id) {
        const clip = job.clips.find((c) => c.id === ev.clip_id);
        if (clip) {
          clip.progress = ev.progress;
          if (ev.stage) clip.stage = ev.stage;
        }
        if (ev.job_id === state.current) updateClipProgress(ev.clip_id, ev.progress, ev.stage);
      } else {
        job.progress = ev.progress;
        if (ev.stage) job.stage = ev.stage;
        if (ev.job_id === state.current) renderStatus(job);
      }
      break;
    }
    case "log": {
      const job = state.jobs[ev.job_id];
      if (!job) return;
      job.logs.push({ t: ev.t, line: ev.line });
      if (ev.job_id === state.current) renderLog(job);
      break;
    }
    case "deleted":
      delete state.jobs[ev.job_id];
      renderJobList();
      if (state.current === ev.job_id) showNew();
      break;
  }
}

// ---------- Sidebar ----------
function renderJobList() {
  const jobs = Object.values(state.jobs).sort((a, b) => b.created_at - a.created_at);
  $("#job-list").innerHTML = jobs.length
    ? jobs.map((j) => {
        const dot = RUNNING.has(j.status) ? "run" : j.status;
        const ready = j.clips.filter((c) => c.status === "ready").length;
        return `<div class="job-item ${j.id === state.current ? "active" : ""}" data-id="${j.id}">
          <div class="name" title="${esc(j.name)}">${esc(j.name)}</div>
          <div class="meta"><span class="dot ${dot}"></span>${STATUS_LABEL[j.status] || j.status} · ${ready} klip</div>
        </div>`;
      }).join("")
    : `<p class="muted small">Belum ada proyek.</p>`;
}
$("#job-list").addEventListener("click", (e) => {
  const item = e.target.closest(".job-item");
  if (item) openJob(item.dataset.id);
});

// ---------- Form proyek baru ----------
function showNew() {
  state.current = null;
  $("#view-new").hidden = false;
  $("#view-job").hidden = true;
  $("#src-video").removeAttribute("src");
  renderJobList();
}
$("#btn-new").onclick = showNew;

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    state.src = tab.dataset.src;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll("[data-src-pane]").forEach((p) => (p.hidden = p.dataset.srcPane !== state.src));
  };
});

function setFile(file) {
  state.file = file;
  $("#drop-label").textContent = file ? `${file.name} · ${(file.size / 1e6).toFixed(1)} MB` : "Tarik video ke sini atau klik untuk memilih";
}
$("#in-file").onchange = (e) => setFile(e.target.files[0]);
const drop = $("#drop");
["dragenter", "dragover"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((n) => drop.addEventListener(n, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});

$("#form-new").onsubmit = (e) => {
  e.preventDefault();
  if (!state.config?.has_key) {
    toast("Isi API key Gemini dulu di Pengaturan.", true);
    openSettings();
    return;
  }
  const fd = new FormData();
  if (state.src === "file") {
    if (!state.file) return toast("Pilih file video dulu.", true);
    fd.append("file", state.file);
  } else {
    const url = $("#in-url").value.trim();
    if (!url) return toast("Masukkan link video.", true);
    fd.append("url", url);
  }
  fd.append("options", JSON.stringify({
    num_clips: +$("#in-num").value, min_len: +$("#in-min").value, max_len: +$("#in-max").value,
    aspect: $("#in-aspect").value, layout: $("#in-layout").value,
    subtitles: $("#in-subs").checked, instructions: $("#in-instr").value,
  }));

  // XHR supaya progres upload file besar terlihat realtime.
  const xhr = new XMLHttpRequest();
  const bar = $("#upload-bar");
  const btn = $("#btn-submit");
  btn.disabled = true;
  bar.hidden = state.src !== "file";
  xhr.upload.onprogress = (ev) => {
    if (!ev.lengthComputable) return;
    const pct = (ev.loaded / ev.total) * 100;
    bar.firstElementChild.style.width = pct + "%";
    $("#form-msg").textContent = pct < 100 ? `Mengunggah ke server lokal… ${pct.toFixed(0)}%` : "Menyimpan file…";
  };
  xhr.onload = () => {
    btn.disabled = false;
    bar.hidden = true;
    $("#form-msg").textContent = "";
    const data = JSON.parse(xhr.responseText || "{}");
    if (xhr.status >= 400) return toast(data.detail || "Gagal membuat proyek", true);
    state.jobs[data.id] = data;
    setFile(null);
    $("#in-file").value = "";
    $("#in-url").value = "";
    openJob(data.id);
  };
  xhr.onerror = () => {
    btn.disabled = false;
    toast("Tidak bisa terhubung ke server lokal.", true);
  };
  xhr.open("POST", "/api/jobs");
  xhr.send(fd);
};

// ---------- Detail proyek ----------
function openJob(id) {
  state.current = id;
  $("#view-new").hidden = true;
  $("#view-job").hidden = false;
  $("#clips").innerHTML = "";
  delete $("#job-format").dataset.job;
  $("#src-video").removeAttribute("src");
  delete $("#src-video").dataset.job;
  renderJobList();
  renderJob();
}

function renderStatus(job) {
  const card = $("#job-status");
  card.className = "card status " + (job.status === "error" ? "error" : job.status === "done" ? "done" : "");
  let pct = job.progress || 0;
  if (job.status === "rendering" && job.clips.length) {
    pct = job.clips.reduce((a, c) => a + (c.status === "ready" ? 1 : c.progress || 0), 0) / job.clips.length;
  }
  const indeterminate = job.status === "analyzing";
  $("#job-stage").textContent = job.status === "error" ? `Gagal: ${job.error}` : job.stage;
  $("#job-pct").textContent = indeterminate || job.status === "queued" ? "…" : `${Math.round(pct * 100)}%`;
  $("#job-bar").style.width = (indeterminate ? 100 : pct * 100) + "%";
  $("#job-bar").style.opacity = indeterminate ? ".35" : "1";
}

function renderLog(job) {
  const pre = $("#job-log");
  const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 20;
  pre.textContent = job.logs.map((l) => `[${new Date(l.t * 1000).toLocaleTimeString()}] ${l.line}`).join("\n");
  if (atBottom) pre.scrollTop = pre.scrollHeight;
}

function renderJob() {
  const job = state.jobs[state.current];
  if (!job) return;
  $("#job-title").textContent = job.name;
  const m = job.meta;
  const o = job.options;
  $("#job-sub").textContent = [
    m ? `${fmt(m.duration)} · ${m.width}×${m.height}` : null,
    `${o.num_clips} klip · ${o.min_len}–${o.max_len} dtk · ${o.aspect} · ${LAYOUT_LABEL[o.layout] || o.layout}`,
    o.subtitles ? "subtitle" : null,
  ].filter(Boolean).join("  ·  ");
  renderStatus(job);
  renderLog(job);

  const sum = $("#job-summary");
  sum.hidden = !job.summary;
  if (job.summary) sum.innerHTML = `<h2>Ringkasan AI</h2><p class="muted">${esc(job.summary)}</p>`;

  const fmtCard = $("#job-format");
  fmtCard.hidden = !job.clips.length;
  if (fmtCard.dataset.job !== job.id) {
    fmtCard.dataset.job = job.id;
    $("#fmt-aspect").value = o.aspect;
    $("#fmt-layout").value = o.layout;
    $("#fmt-subs").checked = o.subtitles;
  }
  $("#btn-rerender-all").disabled = job.clips.some((c) => c.status === "queued" || c.status === "rendering");

  const editor = $("#editor");
  editor.hidden = !job.source;
  const video = $("#src-video");
  if (job.source && video.dataset.job !== job.id) {
    video.dataset.job = job.id;
    video.src = `/media/${job.id}/${encodeURIComponent(job.source)}`;
    $("#man-start").value = fmt(0);
    $("#man-end").value = fmt(Math.min(job.options.min_len, m?.duration || 30));
  }
  renderTimeline();
  renderClips(job);
}

// ---------- Kartu klip (diperbarui di tempat supaya video yang sedang diputar tidak reset) ----------
function renderClips(job) {
  const wrap = $("#clips");
  const ids = new Set(job.clips.map((c) => c.id));
  [...wrap.children].forEach((el) => !ids.has(el.dataset.id) && el.remove());
  const sorted = [...job.clips].sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.start - b.start);
  sorted.forEach((clip, i) => {
    let card = wrap.querySelector(`[data-id="${clip.id}"]`);
    if (!card) {
      card = document.createElement("div");
      card.className = "clip";
      card.dataset.id = clip.id;
      card.innerHTML = `
        <div class="player r-${job.options.aspect.replace(":", "-")}"></div>
        <div class="body">
          <div class="row between"><span class="title"></span><span class="score" hidden></span></div>
          <div class="hook small"></div>
          <div class="reason muted small"></div>
          <div class="tags"></div>
          <div class="times">
            <input class="time c-start" /> <span class="muted">→</span> <input class="time c-end" />
            <span class="dur muted small"></span>
          </div>
          <div class="err" hidden></div>
          <div class="actions">
            <button data-act="rerender">↻ Render ulang</button>
            <button data-act="load">✎ Edit di sumber</button>
            <button data-act="copy">📋 Caption</button>
            <a class="btn dl" data-kind="mp4" hidden>⬇ MP4</a>
            <a class="btn dl-srt" hidden>⬇ SRT</a>
            <button data-act="delete" class="ghost danger">🗑</button>
          </div>
        </div>`;
    }
    if (wrap.children[i] !== card) wrap.insertBefore(card, wrap.children[i] || null);
    updateCard(job, clip, card);
  });
}

function updateCard(job, clip, card) {
  $(".title", card).textContent = clip.title;
  const score = $(".score", card);
  score.hidden = clip.score == null;
  score.textContent = `🔥 ${clip.score}`;
  $(".hook", card).textContent = clip.hook ? `“${clip.hook}”` : "";
  $(".reason", card).textContent = clip.reason || "";
  $(".tags", card).textContent = (clip.hashtags || []).map((t) => (t.startsWith("#") ? t : `#${t}`)).join(" ");
  const s = $(".c-start", card), e = $(".c-end", card);
  if (document.activeElement !== s) s.value = fmt(clip.start);
  if (document.activeElement !== e) e.value = fmt(clip.end);
  $(".dur", card).textContent = `${(clip.end - clip.start).toFixed(1)} dtk`;
  const err = $(".err", card);
  err.hidden = clip.status !== "error";
  err.textContent = clip.error || "";

  const busy = clip.status === "queued" || clip.status === "rendering";
  card.querySelectorAll("button[data-act=rerender], button[data-act=delete]").forEach((b) => (b.disabled = busy));

  const player = $(".player", card);
  player.className = `player r-${job.options.aspect.replace(":", "-")}`;
  if (clip.status === "ready") {
    const src = `/media/${job.id}/${clip.file}?v=${clip.version}`;
    let video = $("video", player);
    if (!video || video.dataset.src !== src) {
      player.innerHTML = `<video controls preload="metadata" playsinline></video>`;
      video = $("video", player);
      video.dataset.src = src;
      video.src = src;
    }
    const dl = $(".dl", card);
    dl.hidden = false;
    dl.href = `/media/${job.id}/${clip.file}?download=1`;
    const srt = $(".dl-srt", card);
    srt.hidden = !clip.srt;
    if (clip.srt) srt.href = `/media/${job.id}/${clip.srt}?download=1`;
  } else {
    const label = { pending: "Menunggu…", queued: "Antre render…", rendering: clip.stage || "Merender…", error: "Gagal render" }[clip.status];
    if (!$(".overlay", player)) player.innerHTML = `<div class="overlay"><div class="lbl"></div><div class="bar"><div></div></div><div class="pct muted small"></div></div>`;
    $(".lbl", player).textContent = label;
    updateClipProgress(clip.id, clip.progress || 0);
  }
}

function updateClipProgress(clipId, p, stage) {
  const card = $(`#clips [data-id="${clipId}"]`);
  if (!card) return;
  const lbl = $(".overlay .lbl", card);
  if (lbl && stage) lbl.textContent = stage;
  const bar = $(".overlay .bar > div", card);
  if (bar) bar.style.width = p * 100 + "%";
  const pct = $(".overlay .pct", card);
  if (pct) pct.textContent = `${Math.round(p * 100)}%`;
  const job = state.jobs[state.current];
  if (job?.status === "rendering") renderStatus(job);
}

$("#clips").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const card = btn.closest(".clip");
  const job = state.jobs[state.current];
  const clip = job.clips.find((c) => c.id === card.dataset.id);
  try {
    if (btn.dataset.act === "rerender") {
      const start = parseTime($(".c-start", card).value), end = parseTime($(".c-end", card).value);
      if (isNaN(start) || isNaN(end)) return toast("Format waktu salah. Gunakan mm:ss.s", true);
      await api(`/api/jobs/${job.id}/clips/${clip.id}`, { method: "PATCH", body: JSON.stringify({ start, end }) });
    } else if (btn.dataset.act === "load") {
      $("#man-start").value = fmt(clip.start);
      $("#man-end").value = fmt(clip.end);
      $("#man-title").value = clip.title;
      const v = $("#src-video");
      v.currentTime = clip.start;
      renderTimeline();
      $("#editor").scrollIntoView({ behavior: "smooth" });
    } else if (btn.dataset.act === "copy") {
      const tags = (clip.hashtags || []).map((t) => (t.startsWith("#") ? t : `#${t}`)).join(" ");
      await navigator.clipboard.writeText([clip.title, clip.hook, tags].filter(Boolean).join("\n\n"));
      toast("Caption disalin.");
    } else if (btn.dataset.act === "delete") {
      if (!confirm(`Hapus klip “${clip.title}”?`)) return;
      await api(`/api/jobs/${job.id}/clips/${clip.id}`, { method: "DELETE" });
    }
  } catch (err) {
    toast(err.message, true);
  }
});

// ---------- Editor manual ----------
const srcVideo = $("#src-video");
let previewEnd = null;

function renderTimeline() {
  const job = state.jobs[state.current];
  const dur = job?.meta?.duration || srcVideo.duration || 0;
  const tl = $("#timeline");
  if (!dur) return;
  tl.querySelectorAll(".mark").forEach((m) => m.remove());
  for (const c of job.clips) {
    const m = document.createElement("div");
    m.className = "mark";
    m.style.left = (c.start / dur) * 100 + "%";
    m.style.width = ((c.end - c.start) / dur) * 100 + "%";
    m.title = c.title;
    tl.prepend(m);
  }
  const s = parseTime($("#man-start").value), e = parseTime($("#man-end").value);
  if (!isNaN(s) && !isNaN(e) && e > s) {
    $("#tl-range").style.left = (s / dur) * 100 + "%";
    $("#tl-range").style.width = ((e - s) / dur) * 100 + "%";
  }
  $("#tl-head").style.left = (srcVideo.currentTime / dur) * 100 + "%";
}

srcVideo.addEventListener("timeupdate", () => {
  renderTimeline();
  if (previewEnd != null && srcVideo.currentTime >= previewEnd) {
    srcVideo.pause();
    previewEnd = null;
  }
});
srcVideo.addEventListener("loadedmetadata", renderTimeline);
$("#timeline").addEventListener("click", (e) => {
  const job = state.jobs[state.current];
  const dur = job?.meta?.duration || srcVideo.duration;
  const rect = e.currentTarget.getBoundingClientRect();
  srcVideo.currentTime = ((e.clientX - rect.left) / rect.width) * dur;
});
["#man-start", "#man-end"].forEach((s) => $(s).addEventListener("input", renderTimeline));

function setIn() { $("#man-start").value = fmt(srcVideo.currentTime); renderTimeline(); }
function setOut() { $("#man-end").value = fmt(srcVideo.currentTime); renderTimeline(); }
$("#btn-in").onclick = setIn;
$("#btn-out").onclick = setOut;
$("#btn-preview").onclick = () => {
  const s = parseTime($("#man-start").value), e = parseTime($("#man-end").value);
  if (isNaN(s) || isNaN(e) || e <= s) return toast("Rentang waktu tidak valid.", true);
  srcVideo.currentTime = s;
  previewEnd = e;
  srcVideo.play();
};
document.addEventListener("keydown", (e) => {
  if ($("#editor").hidden || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
  if (e.key === "i" || e.key === "I") setIn();
  if (e.key === "o" || e.key === "O") setOut();
});
$("#btn-add-clip").onclick = async () => {
  const start = parseTime($("#man-start").value), end = parseTime($("#man-end").value);
  if (isNaN(start) || isNaN(end) || end - start < 1) return toast("Rentang waktu tidak valid (minimal 1 detik).", true);
  try {
    await api(`/api/jobs/${state.current}/clips`, {
      method: "POST",
      body: JSON.stringify({ start, end, title: $("#man-title").value.trim() || null }),
    });
    $("#man-title").value = "";
    toast("Klip ditambahkan, sedang dirender…");
  } catch (err) {
    toast(err.message, true);
  }
};

$("#btn-rerender-all").onclick = async () => {
  try {
    await api(`/api/jobs/${state.current}/rerender`, {
      method: "POST",
      body: JSON.stringify({ aspect: $("#fmt-aspect").value, layout: $("#fmt-layout").value, subtitles: $("#fmt-subs").checked }),
    });
    toast("Semua klip sedang dirender ulang…");
  } catch (err) {
    toast(err.message, true);
  }
};

$("#btn-delete-job").onclick = async () => {
  const job = state.jobs[state.current];
  if (!confirm(`Hapus proyek “${job.name}” beserta semua klipnya?`)) return;
  try {
    await api(`/api/jobs/${job.id}`, { method: "DELETE" });
  } catch (err) {
    toast(err.message, true);
  }
};

// ---------- Pengaturan ----------
async function loadConfig() {
  state.config = await api("/api/config");
  const sel = $("#set-model");
  if (![...sel.options].some((o) => o.value === state.config.model)) {
    sel.add(new Option(state.config.model, state.config.model));
  }
  sel.value = state.config.model;
  const wsel = $("#set-whisper");
  wsel.innerHTML = "";
  for (const [name, desc] of Object.entries(state.config.whisper_models)) {
    const ready = state.config.whisper_downloaded[name] ? "✓ " : "";
    wsel.add(new Option(`${ready}${name} — ${desc}`, name));
  }
  wsel.value = state.config.whisper_model;
  const lsel = $("#set-lang");
  lsel.innerHTML = "";
  for (const [code, label] of Object.entries(state.config.whisper_languages)) lsel.add(new Option(label, code));
  lsel.value = state.config.whisper_language;
  $("#set-key-hint").textContent = state.config.has_key ? `Tersimpan (${state.config.key_hint}). Kosongkan jika tidak ingin mengganti.` : "Belum diisi.";
  $("#set-info").textContent = `ffmpeg: ${state.config.ffmpeg.split("/").pop()} · subtitle: ${state.config.subtitles_supported ? "didukung" : "tidak didukung"} · deteksi wajah: ${state.config.face_tracking ? "aktif" : "tidak tersedia"}`;
  if (!state.config.has_key) openSettings();
}
function openSettings() {
  if (!$("#dlg-settings").open) $("#dlg-settings").showModal();
}
$("#btn-settings").onclick = openSettings;
$("#btn-load-models").onclick = async () => {
  const btn = $("#btn-load-models");
  btn.disabled = true;
  try {
    const key = $("#set-key").value.trim();
    if (key) await api("/api/config", { method: "POST", body: JSON.stringify({ api_key: key }) });
    const { models } = await api("/api/models");
    const sel = $("#set-model");
    const current = sel.value;
    sel.innerHTML = "";
    models.forEach((m) => sel.add(new Option(m, m)));
    if (models.includes(current)) sel.value = current;
    toast(`Terhubung ke Gemini · ${models.length} model tersedia`);
    await loadConfig();
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
  }
};
$("#btn-save-settings").onclick = async (e) => {
  e.preventDefault();
  try {
    await api("/api/config", {
      method: "POST",
      body: JSON.stringify({
        api_key: $("#set-key").value.trim() || null, model: $("#set-model").value,
        whisper_model: $("#set-whisper").value, whisper_language: $("#set-lang").value,
      }),
    });
    $("#set-key").value = "";
    await loadConfig();
    $("#dlg-settings").close();
    toast("Pengaturan disimpan.");
  } catch (err) {
    toast(err.message, true);
  }
};

loadConfig().catch((err) => toast(err.message, true));
connect();
