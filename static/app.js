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
      if ((ev.job.usage || []).length !== (state.jobs[ev.job.id]?.usage || []).length) scheduleUsageRefresh();
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
        if (ev.job_id === state.current) {
          if (clip?.publish?.status === "uploading") {
            clip.publish.progress = ev.progress;
            const card = $(`#clips [data-id="${ev.clip_id}"]`);
            if (card) renderPublishState(job, clip, card);
          } else {
            updateClipProgress(ev.clip_id, ev.progress, ev.stage);
          }
        }
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

// ---------- Pemakaian & biaya AI ----------
const nf = new Intl.NumberFormat("id-ID");
function fmtTokens(n) {
  return n >= 1e6 ? `${(n / 1e6).toLocaleString("id-ID", { maximumFractionDigits: 2 })} jt` : nf.format(n || 0);
}
function fmtMoney(usd, short = false) {
  if (usd == null) return "—";
  const rate = state.config?.pricing?.usd_idr;
  const dollars = `$${usd < 0.01 && usd > 0 ? usd.toFixed(4) : usd.toFixed(usd < 1 ? 3 : 2)}`;
  if (!rate) return dollars;
  const rupiah = `Rp${nf.format(Math.round(usd * rate))}`;
  return short ? rupiah : `${rupiah} (${dollars})`;
}
function jobCost(job) {
  const entries = job.usage || [];
  if (!entries.length) return null;
  return entries.reduce((a, e) => a + (e.cost_usd || 0), 0);
}

function renderJobUsage(job) {
  const card = $("#job-usage");
  const entries = job.usage || [];
  const aiClips = job.clips.filter((c) => c.score != null).length;
  if (!entries.length) {
    // Proyek lama yang sudah dianalisis sebelum pencatatan token ada.
    card.hidden = !(job.summary && job.status === "done");
    card.innerHTML = `<h2>🤖 Pemakaian AI</h2><p class="muted small">Tidak tercatat: proyek ini dianalisis sebelum fitur pencatatan token ditambahkan.</p>`;
    return;
  }
  const sum = (k) => entries.reduce((a, e) => a + (e[k] || 0), 0);
  const usd = jobCost(job);
  const unpriced = entries.some((e) => e.cost_usd == null);
  const tier = entries[entries.length - 1].tier;
  const models = [...new Set(entries.map((e) => e.model))].join(", ");
  const perClip = aiClips && usd != null ? fmtMoney(usd / aiClips) : "—";
  const item = (k, v) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`;
  card.hidden = false;
  card.innerHTML = `
    <div class="row between"><h2>🤖 Pemakaian AI</h2><span class="muted small">${esc(models)} · ${entries.length} panggilan</span></div>
    <div class="usage-grid">
      ${item("Biaya", unpriced ? "harga model belum diatur" : tier === "free" ? "Gratis (tier Free)" : fmtMoney(usd))}
      ${item("Per klip AI", tier === "free" ? "—" : perClip)}
      ${item("Token input", fmtTokens(sum("prompt_tokens")))}
      ${item("↳ video / audio / teks", `${fmtTokens(sum("video_tokens"))} / ${fmtTokens(sum("audio_tokens"))} / ${fmtTokens(sum("text_tokens"))}`)}
      ${item("Token output", fmtTokens(sum("output_tokens")))}
      ${item("↳ thinking", fmtTokens(sum("thoughts_tokens")))}
    </div>
    <p class="muted small">Subtitle (Whisper), deteksi wajah, pemotongan jeda, dan render berjalan lokal: Rp0.</p>`;
}

let usageTimer;
function scheduleUsageRefresh() {
  clearTimeout(usageTimer);
  usageTimer = setTimeout(loadUsage, 800);
}

async function loadUsage() {
  try {
    const data = await api("/api/usage");
    state.usage = data;
    state.config && (state.config.pricing = data.pricing);
    $("#usage-month").textContent = data.month.calls ? `· ${fmtMoney(data.month.usd, true)} bln ini` : "";
    if (!$("#view-usage").hidden) renderUsage();
  } catch (err) {
    console.warn(err);
  }
}

function renderUsage() {
  const d = state.usage;
  if (!d) return;
  const tile = (label, value, sub) => `<div class="tile"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`;
  const free = d.pricing.tier === "free";
  $("#usage-tiles").innerHTML = [
    tile("Biaya bulan ini", free ? "Rp0" : fmtMoney(d.month.usd, true), `${d.month.calls} analisis · ${fmtTokens(d.month.total_tokens)} token`),
    tile("Total biaya", free ? "Rp0" : fmtMoney(d.total.usd, true), state.config?.pricing?.usd_idr ? `$${d.total.usd.toFixed(3)}` : "isi kurs untuk Rupiah"),
    tile("Total token", fmtTokens(d.total.total_tokens), `${fmtTokens(d.total.prompt_tokens)} input · ${fmtTokens(d.total.output_tokens)} output`),
    tile("Rata-rata per analisis", d.total.calls ? fmtMoney(d.total.usd / d.total.calls, true) : "—",
      d.untracked_projects ? `${d.untracked_projects} proyek lama tidak tercatat` : `${d.total.calls} analisis tercatat`),
  ].join("");

  const days = Object.entries(d.per_day);
  const max = Math.max(...days.map(([, v]) => v.usd), 0.000001);
  $("#usage-days").innerHTML = days.length
    ? days.map(([day, v]) => `<div class="day" title="${new Date(day).toLocaleDateString("id-ID", { day: "numeric", month: "short" })}: ${fmtMoney(v.usd)} · ${fmtTokens(v.total_tokens)} token">
        <div class="fill" style="height:${(v.usd / max) * 100}%"></div></div>`).join("")
    : `<p class="muted small">Belum ada pemakaian tercatat.</p>`;

  $("#usage-projects").innerHTML = `<tr><th>Proyek</th><th>Tanggal</th><th class="num">Durasi video</th><th class="num">Klip</th><th class="num">Token</th><th class="num">Biaya</th></tr>` +
    d.projects.map((p) => `<tr class="link" data-id="${p.id}">
      <td>${esc(p.name.length > 48 ? p.name.slice(0, 47) + "…" : p.name)}</td>
      <td>${new Date(p.created_at * 1000).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" })}</td>
      <td class="num">${p.video_seconds ? fmt(p.video_seconds) : "—"}</td>
      <td class="num">${p.clips}</td>
      <td class="num">${p.tracked ? fmtTokens(p.total_tokens) : "—"}</td>
      <td class="num">${!p.tracked ? '<span class="muted">tidak tercatat</span>' : p.unpriced ? "—" : fmtMoney(p.usd)}</td></tr>`).join("");

  const models = Object.entries(d.per_model);
  $("#usage-models").innerHTML = models.length
    ? `<tr><th>Model</th><th class="num">Analisis</th><th class="num">Input</th><th class="num">Output</th><th class="num">Biaya</th></tr>` +
      models.map(([m, v]) => `<tr><td>${esc(m)}</td><td class="num">${v.calls}</td><td class="num">${fmtTokens(v.prompt_tokens)}</td><td class="num">${fmtTokens(v.output_tokens)}</td><td class="num">${v.unpriced ? "—" : fmtMoney(v.usd)}</td></tr>`).join("")
    : `<tr><td class="muted">Belum ada.</td></tr>`;

  const pr = d.pricing;
  const p = pr.price;
  $("#price-info").innerHTML = p
    ? `Model aktif <b>${esc(pr.model)}</b>: input $${p.input} · audio $${p.audio} · output $${p.output} per 1 juta token ` +
      (p.source === "manual" ? "(harga manual)." : `(harga resmi berlaku sejak ${p.effective_from === "2000-01-01" ? "awal" : p.effective_from}, <a href="${pr.source_url}" target="_blank" rel="noopener">sumber</a>).`)
    : `Harga untuk <b>${esc(pr.model)}</b> belum ada di tabel. Isi harga manual supaya biaya bisa dihitung.`;
  $("#price-tier").value = pr.tier;
  if (document.activeElement !== $("#price-rate")) $("#price-rate").value = pr.usd_idr || "";
  const o = pr.override || {};
  $("#price-input").value = o.input ?? "";
  $("#price-audio").value = o.audio ?? "";
  $("#price-output").value = o.output ?? "";
}

function showUsage() {
  state.current = null;
  $("#view-new").hidden = true;
  $("#view-job").hidden = true;
  $("#view-usage").hidden = false;
  $("#src-video").removeAttribute("src");
  renderJobList();
  renderUsage();
  loadUsage();
}
$("#btn-usage").onclick = showUsage;
$("#usage-projects").addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-id]");
  if (row && state.jobs[row.dataset.id]) openJob(row.dataset.id);
});

async function savePricing(extra = {}) {
  const num = (id) => ($(id).value === "" ? null : Number($(id).value));
  const body = { tier: $("#price-tier").value, usd_idr: num("#price-rate") ?? 0, ...extra };
  if (!extra.clear_override && num("#price-input") != null && num("#price-output") != null) {
    Object.assign(body, { input: num("#price-input"), audio: num("#price-audio"), output: num("#price-output") });
  }
  const info = await api("/api/pricing", { method: "POST", body: JSON.stringify(body) });
  state.config.pricing = info;
}
$("#btn-price-save").onclick = async () => {
  try {
    await savePricing();
    await loadUsage();
    renderJobList();
    toast("Pengaturan harga disimpan. Berlaku untuk analisis berikutnya.");
  } catch (err) {
    toast(err.message, true);
  }
};
$("#btn-price-reset").onclick = async () => {
  try {
    await savePricing({ clear_override: true });
    await loadUsage();
    toast("Kembali memakai harga resmi.");
  } catch (err) {
    toast(err.message, true);
  }
};
$("#btn-recalc").onclick = async () => {
  if (!confirm("Hitung ulang biaya semua riwayat dengan tier & harga saat ini?")) return;
  try {
    await savePricing();
    const r = await api("/api/usage/recalculate", { method: "POST" });
    await loadUsage();
    toast(`${r.recalculated} catatan dihitung ulang.`);
  } catch (err) {
    toast(err.message, true);
  }
};

// Perkiraan biaya sebelum proses dimulai.
let estimateTimer;
function updateEstimate() {
  clearTimeout(estimateTimer);
  estimateTimer = setTimeout(async () => {
    const box = $("#estimate");
    const duration = state.src === "file" ? state.fileDuration : null;
    if (!duration) return (box.hidden = true);
    const q = new URLSearchParams({ duration, num_clips: $("#in-num").value, max_len: $("#in-max").value, subtitles: $("#in-subs").checked });
    try {
      const e = await api(`/api/estimate?${q}`);
      const money = e.tier === "free" ? "gratis (tier Free)" : e.usd == null ? "harga model belum diatur" : `≈ ${fmtMoney(e.usd)}`;
      box.innerHTML = `🤖 Perkiraan pemakaian AI (${esc(e.model)}): ~${fmtTokens(e.prompt_tokens)} token input + ~${fmtTokens(e.output_tokens)} output → <b>${money}</b>` +
        (e.low_res ? ` <span class="muted">· video &gt; 20 menit dianalisis resolusi rendah</span>` : "");
      box.hidden = false;
    } catch {
      box.hidden = true;
    }
  }, 250);
}
["#in-num", "#in-max", "#in-subs"].forEach((sel) => $(sel).addEventListener("input", updateEstimate));

// ---------- Sidebar ----------
function renderJobList() {
  const jobs = Object.values(state.jobs).sort((a, b) => b.created_at - a.created_at);
  $("#job-list").innerHTML = jobs.length
    ? jobs.map((j) => {
        const dot = RUNNING.has(j.status) ? "run" : j.status;
        const ready = j.clips.filter((c) => c.status === "ready").length;
        const usd = jobCost(j);
        return `<div class="job-item ${j.id === state.current ? "active" : ""}" data-id="${j.id}">
          <div class="name" title="${esc(j.name)}">${esc(j.name)}</div>
          <div class="meta"><span class="dot ${dot}"></span>${STATUS_LABEL[j.status] || j.status} · ${ready} klip${usd != null ? `<span class="cost">${fmtMoney(usd, true)}</span>` : ""}</div>
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
  $("#view-usage").hidden = true;
  $("#src-video").removeAttribute("src");
  renderJobList();
}
$("#btn-new").onclick = showNew;

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    state.src = tab.dataset.src;
    updateEstimate();
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll("[data-src-pane]").forEach((p) => (p.hidden = p.dataset.srcPane !== state.src));
  };
});

function setFile(file) {
  state.file = file;
  state.fileDuration = null;
  updateEstimate();
  if (file) {
    const probe = document.createElement("video");
    probe.preload = "metadata";
    probe.onloadedmetadata = () => {
      state.fileDuration = probe.duration;
      URL.revokeObjectURL(probe.src);
      updateEstimate();
    };
    probe.src = URL.createObjectURL(file);
  }
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
    subtitles: $("#in-subs").checked, remove_silence: $("#in-trim").checked,
    show_title: $("#in-title").checked, instructions: $("#in-instr").value,
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
  $("#view-usage").hidden = true;
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
    o.remove_silence ? "tanpa jeda" : null,
    o.show_title ? "judul" : null,
  ].filter(Boolean).join("  ·  ");
  renderStatus(job);
  renderLog(job);

  const sum = $("#job-summary");
  sum.hidden = !job.summary;
  if (job.summary) sum.innerHTML = `<h2>Ringkasan AI</h2><p class="muted">${esc(job.summary)}</p>`;

  renderJobUsage(job);

  const fmtCard = $("#job-format");
  fmtCard.hidden = !job.clips.length;
  if (fmtCard.dataset.job !== job.id) {
    fmtCard.dataset.job = job.id;
    $("#fmt-aspect").value = o.aspect;
    $("#fmt-layout").value = o.layout;
    $("#fmt-subs").checked = o.subtitles;
    $("#fmt-trim").checked = !!o.remove_silence;
    $("#fmt-title").checked = !!o.show_title;
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
          <div class="row between"><input class="title grow" title="Judul yang tampil di atas video" /><span class="score" hidden></span></div>
          <div class="hook small"></div>
          <div class="reason muted small"></div>
          <div class="tags"></div>
          <div class="times">
            <input class="time c-start" /> <span class="muted">→</span> <input class="time c-end" />
            <span class="dur muted small"></span>
          </div>
          <div class="err" hidden></div>
          <div class="pubstate" hidden></div>
          <div class="actions">
            <button data-act="rerender">↻ Render ulang</button>
            <button data-act="load">✎ Edit di sumber</button>
            <button data-act="copy">📋 Caption</button>
            <button data-act="publish">📤 Posting</button>
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
  const titleInput = $(".title", card);
  if (document.activeElement !== titleInput) titleInput.value = clip.title;
  const score = $(".score", card);
  score.hidden = clip.score == null;
  score.textContent = `🔥 ${clip.score}`;
  $(".hook", card).textContent = clip.hook ? `“${clip.hook}”` : "";
  $(".reason", card).textContent = clip.reason || "";
  $(".tags", card).textContent = (clip.hashtags || []).map((t) => (t.startsWith("#") ? t : `#${t}`)).join(" ");
  const s = $(".c-start", card), e = $(".c-end", card);
  if (document.activeElement !== s) s.value = fmt(clip.start);
  if (document.activeElement !== e) e.value = fmt(clip.end);
  const span = clip.end - clip.start;
  const out = clip.duration_out;
  $(".dur", card).textContent = out && out < span - 0.2 ? `${span.toFixed(1)} → ${out.toFixed(1)} dtk` : `${span.toFixed(1)} dtk`;
  $(".dur", card).title = out && out < span - 0.2 ? "Durasi setelah jeda diam dibuang" : "";
  const err = $(".err", card);
  err.hidden = clip.status !== "error";
  err.textContent = clip.error || "";

  const busy = clip.status === "queued" || clip.status === "rendering";
  card.querySelectorAll("button[data-act=rerender], button[data-act=delete]").forEach((b) => (b.disabled = busy));
  const posting = ["uploading", "posting"].includes(clip.publish?.status);
  $("button[data-act=publish]", card).disabled = clip.status !== "ready" || posting;
  renderPublishState(job, clip, card);

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

const SERVICE_LABEL = { instagram: "Instagram", tiktok: "TikTok", youtube: "YouTube", facebook: "Facebook",
  linkedin: "LinkedIn", twitter: "X", threads: "Threads", bluesky: "Bluesky", mastodon: "Mastodon",
  pinterest: "Pinterest", googlebusiness: "Google Business" };
const POST_STATUS = { scheduled: "terjadwal", sending: "sedang dikirim", sent: "terkirim", error: "gagal",
  draft: "draf", needs_approval: "menunggu persetujuan" };

function renderPublishState(job, clip, card) {
  const box = $(".pubstate", card);
  const pub = clip.publish;
  box.hidden = !pub;
  if (!pub) return;
  let head = "";
  if (pub.status === "uploading") head = `☁️ Mengunggah video… ${Math.round((pub.progress || 0) * 100)}%`;
  else if (pub.status === "posting") head = "📤 Mengirim ke Buffer…";
  else if (pub.status === "error" && !pub.results.length) head = `<span class="bad">❌ ${esc(pub.error)}</span>`;
  else head = `📤 Posting · <button type="button" class="ghost small-btn" data-act="pubrefresh">↻ Cek status</button>`;
  const when = (iso) => (iso ? new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "");
  const rows = pub.results.map((r) => {
    const name = `${SERVICE_LABEL[r.service] || r.service} · ${esc(r.channel)}`;
    if (!r.ok) return `<div class="bad">✗ ${name}: ${esc(r.error)}</div>`;
    const status = POST_STATUS[r.status] || r.status || "terkirim";
    const extra = r.error ? ` — ${esc(r.error)}` : r.link ? ` — <a href="${esc(r.link)}" target="_blank" rel="noopener">lihat</a>` : r.due_at && r.status === "scheduled" ? ` ${when(r.due_at)}` : "";
    return `<div class="${r.status === "error" ? "bad" : "ok"}">✓ ${name}: ${status}${extra}</div>`;
  });
  box.innerHTML = `<div>${head}</div>${rows.join("")}`;
}

// ---------- Posting via Buffer ----------
const pub = { job: null, clip: null, channels: [] };

function clipCaption(clip) {
  const tags = (clip.hashtags || []).map((t) => (t.startsWith("#") ? t : `#${t}`)).join(" ");
  return [clip.title, clip.hook, tags].filter(Boolean).join("\n\n");
}

async function loadChannels(refresh = false) {
  const box = $("#pub-channels");
  box.innerHTML = `<p class="muted small">Memuat channel…</p>`;
  try {
    const { channels } = await api(`/api/buffer/channels${refresh ? "?refresh=true" : ""}`);
    pub.channels = channels;
    if (!channels.length) {
      box.innerHTML = `<p class="muted small">Belum ada channel di Buffer. Hubungkan akun sosial media di publish.buffer.com.</p>`;
      return;
    }
    let remembered = [];
    try { remembered = JSON.parse(localStorage.getItem("pubChannels") || "[]"); } catch {}
    box.innerHTML = channels.map((c) => {
      const off = c.isDisconnected || c.isLocked || !c.supportsVideo;
      const why = c.isDisconnected ? "terputus" : c.isLocked ? "terkunci" : !c.supportsVideo ? "tidak mendukung video" : "";
      return `<label class="channel ${off ? "off" : ""}">
        <input type="checkbox" value="${esc(c.id)}" ${off ? "disabled" : ""} ${!off && remembered.includes(c.id) ? "checked" : ""} />
        ${c.avatar ? `<img src="${esc(c.avatar)}" alt="" referrerpolicy="no-referrer" />` : ""}
        <span>${esc(c.displayName || c.name)}</span>
        <span class="svc">${SERVICE_LABEL[c.service] || esc(c.service)}${why ? ` · ${why}` : ""}</span>
      </label>`;
    }).join("");
  } catch (err) {
    box.innerHTML = `<p class="err">${esc(err.message)}</p>`;
  }
}

function updateCount() {
  const n = $("#pub-text").value.length;
  const selected = [...$("#pub-channels").querySelectorAll("input:checked")].map((i) => pub.channels.find((c) => c.id === i.value));
  const warn = selected.some((c) => c?.service === "twitter") && n > 280 ? " · melebihi 280 karakter untuk X" : "";
  $("#pub-count").textContent = `${n} karakter${warn}`;
}

function openPublish(job, clip) {
  pub.job = job;
  pub.clip = clip;
  $("#pub-clip").textContent = `“${clip.title}” · ${(clip.duration_out || clip.end - clip.start).toFixed(1)} dtk`;
  $("#pub-text").value = clipCaption(clip);
  $("#pub-mode").value = "addToQueue";
  $("#pub-when-wrap").hidden = true;
  updateCount();
  $("#dlg-publish").showModal();
  loadChannels();
}

$("#pub-text").addEventListener("input", updateCount);
$("#pub-channels").addEventListener("change", updateCount);
$("#btn-pub-refresh").onclick = () => loadChannels(true);
$("#pub-mode").onchange = () => ($("#pub-when-wrap").hidden = $("#pub-mode").value !== "customScheduled");
$("#form-publish").onsubmit = async (e) => {
  e.preventDefault();
  const ids = [...$("#pub-channels").querySelectorAll("input:checked")].map((i) => i.value);
  if (!ids.length) return toast("Pilih minimal satu channel.", true);
  const mode = $("#pub-mode").value;
  let due_at = null;
  if (mode === "customScheduled") {
    if (!$("#pub-when").value) return toast("Isi tanggal & jam jadwal.", true);
    due_at = new Date($("#pub-when").value).toISOString();
  }
  const names = ids.map((id) => pub.channels.find((c) => c.id === id)).map((c) => c.displayName || c.name).join(", ");
  const verb = mode === "shareNow" ? "langsung dipublikasikan" : "dijadwalkan";
  if (!confirm(`Klip akan ${verb} ke: ${names}. Lanjutkan?`)) return;
  const btn = $("#btn-pub-send");
  btn.disabled = true;
  try {
    await api(`/api/jobs/${pub.job.id}/clips/${pub.clip.id}/publish`, {
      method: "POST", body: JSON.stringify({ channel_ids: ids, text: $("#pub-text").value, mode, due_at }),
    });
    try { localStorage.setItem("pubChannels", JSON.stringify(ids)); } catch {}
    $("#dlg-publish").close();
    toast("Sedang mengunggah & mengirim ke Buffer…");
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
  }
};

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
      const title = $(".title", card).value.trim() || null;
      await api(`/api/jobs/${job.id}/clips/${clip.id}`, { method: "PATCH", body: JSON.stringify({ start, end, title }) });
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
    } else if (btn.dataset.act === "publish") {
      openPublish(job, clip);
    } else if (btn.dataset.act === "pubrefresh") {
      await api(`/api/jobs/${job.id}/clips/${clip.id}/publish/refresh`, { method: "POST" });
      toast("Status posting diperbarui.");
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
      body: JSON.stringify({
        aspect: $("#fmt-aspect").value, layout: $("#fmt-layout").value, subtitles: $("#fmt-subs").checked,
        remove_silence: $("#fmt-trim").checked, show_title: $("#fmt-title").checked,
      }),
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
  fillSettings();
  if (!state.config.has_key) openSettings();
}

// Isian yang sedang diedit (belum disimpan) tidak boleh tertimpa saat konfigurasi dimuat ulang.
const settingsForm = $("#form-settings");
settingsForm.addEventListener("input", (e) => (e.target.dataset.dirty = "1"));
// Enter di kolom isian = Simpan (bukan menutup dialog).
settingsForm.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.tagName === "INPUT" && !e.isComposing) {
    e.preventDefault();
    settingsForm.requestSubmit();
  }
});
function clearDirty() {
  settingsForm.querySelectorAll("[data-dirty]").forEach((el) => delete el.dataset.dirty);
}
function setField(el, value) {
  if (!el.dataset.dirty) el.value = value;
}

function fillSettings() {
  const cfg = state.config;
  const sel = $("#set-model");
  if (![...sel.options].some((o) => o.value === cfg.model)) sel.add(new Option(cfg.model, cfg.model));
  setField(sel, cfg.model);
  const wsel = $("#set-whisper");
  const wval = wsel.dataset.dirty ? wsel.value : cfg.whisper_model;
  wsel.innerHTML = "";
  for (const [name, desc] of Object.entries(cfg.whisper_models)) {
    wsel.add(new Option(`${cfg.whisper_downloaded[name] ? "✓ " : ""}${name} — ${desc}`, name));
  }
  wsel.value = wval;
  const lsel = $("#set-lang");
  const lval = lsel.dataset.dirty ? lsel.value : cfg.whisper_language;
  lsel.innerHTML = "";
  for (const [code, label] of Object.entries(cfg.whisper_languages)) lsel.add(new Option(label, code));
  lsel.value = lval;
  $("#set-buffer-hint").textContent = cfg.buffer_key_hint ? `Tersimpan (${cfg.buffer_key_hint}).` : "Belum diisi.";
  setField($("#set-host"), cfg.media_host);
  showHostFields();
  document.querySelectorAll("[data-env]").forEach((input) => {
    const value = cfg.media[input.dataset.env] || "";
    if (input.type === "password") {
      setField(input, "");
      input.placeholder = value ? `Tersimpan (${value})` : "Belum diisi";
    } else {
      setField(input, value);
    }
  });
  const missing = $("#host-missing");
  const sameHost = $("#set-host").value === cfg.media_host;
  missing.hidden = !(sameHost && cfg.media_missing.length);
  missing.textContent = `⚠️ Belum tersimpan: ${cfg.media_missing.join(", ")}. Isi lalu klik Simpan.`;
  $("#set-key-hint").textContent = cfg.has_key ? `Tersimpan (${cfg.key_hint}). Kosongkan jika tidak ingin mengganti.` : "Belum diisi.";
  $("#set-info").textContent = `ffmpeg: ${cfg.ffmpeg.split("/").pop()} · subtitle: ${cfg.subtitles_supported ? "didukung" : "tidak didukung"} · deteksi wajah: ${cfg.face_tracking ? "aktif" : "tidak tersedia"}`;
}

function openSettings() {
  if ($("#dlg-settings").open) return;
  clearDirty();
  if (state.config) fillSettings();
  $("#host-test").textContent = "";
  $("#buffer-test").textContent = "";
  $("#dlg-settings").showModal();
}
document.querySelectorAll("[data-close]").forEach((btn) => (btn.onclick = () => $(`#${btn.dataset.close}`).close()));
$("#btn-settings").onclick = openSettings;
function showHostFields() {
  document.querySelectorAll("[data-host]").forEach((el) => (el.hidden = el.dataset.host !== $("#set-host").value));
}
$("#set-host").onchange = showHostFields;
$("#btn-test-buffer").onclick = async () => {
  const out = $("#buffer-test");
  out.textContent = "Menghubungkan…";
  try {
    const key = $("#set-buffer").value.trim();
    if (key) await api("/api/config", { method: "POST", body: JSON.stringify({ buffer_api_key: key }) });
    const { channels } = await api("/api/buffer/channels?refresh=true");
    out.textContent = `✓ Terhubung · ${channels.length} channel`;
    $("#set-buffer").value = "";
    delete $("#set-buffer").dataset.dirty;
    state.config = await api("/api/config");
    fillSettings();
  } catch (err) {
    out.textContent = `✗ ${err.message}`;
  }
};
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
    $("#set-key").value = "";
    delete $("#set-key").dataset.dirty;
    state.config = await api("/api/config");
    fillSettings();
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
  }
};
function hostFields() {
  return Object.fromEntries([...document.querySelectorAll(`[data-host="${$("#set-host").value}"] [data-env]`)]
    .map((i) => [i.dataset.env, i.value.trim()]));
}
async function saveSettings() {
  await api("/api/config", {
    method: "POST",
    body: JSON.stringify({
      api_key: $("#set-key").value.trim() || null, model: $("#set-model").value,
      whisper_model: $("#set-whisper").value, whisper_language: $("#set-lang").value,
      buffer_api_key: $("#set-buffer").value.trim() || null,
      media_host: $("#set-host").value, media: hostFields(),
    }),
  });
  $("#set-key").value = "";
  $("#set-buffer").value = "";
  clearDirty();
  state.config = await api("/api/config");
  fillSettings();
}
// Tombol Simpan maupun Enter di kolom isian sama-sama menyimpan.
settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#btn-save-settings");
  btn.disabled = true;
  try {
    await saveSettings();
    if (state.config.media_missing.length) {
      toast(`Tersimpan, tapi hosting video belum lengkap: ${state.config.media_missing.join(", ")}.`, true);
    } else {
      $("#dlg-settings").close();
      toast("Pengaturan disimpan.");
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
  }
});
$("#btn-test-host").onclick = async () => {
  const out = $("#host-test");
  out.textContent = "Mengecek…";
  try {
    // Simpan dulu isian hosting yang baru diketik supaya yang dites adalah nilai terbaru.
    await api("/api/config", { method: "POST", body: JSON.stringify({ media_host: $("#set-host").value, media: hostFields() }) });
    document.querySelectorAll("[data-env]").forEach((el) => delete el.dataset.dirty);
    delete $("#set-host").dataset.dirty;
    state.config = await api("/api/config");
    fillSettings();
    const r = await api("/api/mediahost/test", { method: "POST" });
    out.textContent = `✓ ${r.message}`;
  } catch (err) {
    out.textContent = `✗ ${err.message}`;
  }
};

loadConfig().then(loadUsage).catch((err) => toast(err.message, true));
connect();
