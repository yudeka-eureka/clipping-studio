"use strict";

const $ = (s, el = document) => el.querySelector(s);
const state = { jobs: {}, current: null, src: "file", file: null, config: null,
  searchQuery: "", activeFilter: "all", user: null };
const ALL_VIEWS = ["#view-new", "#view-job", "#view-usage", "#view-settings", "#view-auth"];

function setView(activeViewId) {
  for (const v of ALL_VIEWS) {
    const el = $(v);
    if (el) el.hidden = v !== activeViewId;
  }
  const appLayout = $("#app-layout");
  const sidebar = $("#sidebar");
  const isSettings = activeViewId === "#view-settings";
  if (appLayout) {
    appLayout.classList.toggle("in-settings", isSettings);
  }
  if (sidebar) {
    sidebar.hidden = isSettings;
  }
}
const AI_STORAGE_KEY = "clipping-studio-ai";
const USER_CONFIG_KEY = "clipping_user_config";
const USER_TOKEN_KEY = "clipping_user_token";
const USER_MEDIA_KEY = "clipping_user_media";

function getStoredToken() {
  return state.user?.credential_token || "";
}

async function loadAiCredentials() {
  try {
    const res = await api("/api/credentials/ai");
    state.aiCredentials = res;
    if (state.config && res.providers) {
      for (const [name, p] of Object.entries(res.providers)) {
        if (state.config.providers?.[name]) {
          state.config.providers[name].has_key = p.has_key;
          state.config.providers[name].key_hint = p.key_hint;
          if (p.model) state.config.providers[name].model = p.model;
        }
      }
      if (res.provider) state.config.provider = res.provider;
    }
    return res;
  } catch {
    return null;
  }
}

async function loadMediaCredentials() {
  try {
    const res = await api("/api/credentials/media");
    state.mediaCredentials = res;
    return res;
  } catch {
    return null;
  }
}

function userHasCustomMedia() {
  const mc = state.mediaCredentials;
  if (!mc) return false;
  const host = mc.host || "default";
  return Boolean(mc.configured?.[host]);
}

function getActiveMediaContext() {
  const host = state.mediaCredentials?.host || "default";
  return { provider: host, credentials: {} };
}

function getUserConfig() {
  try {
    const raw = localStorage.getItem(USER_CONFIG_KEY) || "{}";
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

function saveUserConfig(cfg) {
  try {
    localStorage.setItem(USER_CONFIG_KEY, JSON.stringify(cfg));
  } catch {}
}

function aiHeaders(providerOverride) {
  const userCfg = getUserConfig();
  const provider = providerOverride || userCfg.provider || state.aiCredentials?.provider || state.config?.provider || "gemini";
  const profile = (state.aiCredentials?.providers || {})[provider] || {};
  const configModel = state.config?.providers?.[provider]?.model || "";
  return {
    "X-AI-Provider": provider,
    "X-AI-Model": profile.model || configModel,
  };
}

const UNAVAILABLE_MODEL_PATTERNS = ["2.5-flash", "2.5-pro", "2.5-flash-lite", "1.0-pro"];

function isModelUnavailable(modelName) {
  if (!modelName) return false;
  return UNAVAILABLE_MODEL_PATTERNS.some((pat) => modelName.includes(pat));
}

function applyStoredAi(cfg) {
  if (!cfg) return cfg;
  const userCfg = getUserConfig();
  const aiCreds = state.aiCredentials || {};
  const provider = userCfg.provider || aiCreds.provider || cfg.provider;

  if (cfg.providers && aiCreds.providers) {
    for (const [name, p] of Object.entries(cfg.providers)) {
      const profile = aiCreds.providers[name] || {};
      if (profile.has_key) {
        p.has_key = true;
        p.key_hint = profile.key_hint;
      }
      if (profile.model) {
        if (isModelUnavailable(profile.model)) {
          profile.model = p.default_model || "gemini-3.8-flash";
        }
        p.model = profile.model;
      }
    }
  }

  cfg.provider = provider;
  if (cfg.providers && cfg.providers[provider]) {
    cfg.model = cfg.providers[provider].model || cfg.model;
    if (isModelUnavailable(cfg.model)) {
      cfg.model = cfg.providers[provider].default_model || "gemini-3.8-flash";
    }
  }
  if (userCfg.whisper_model && cfg.whisper_models && cfg.whisper_models[userCfg.whisper_model]) {
    cfg.whisper_model = userCfg.whisper_model;
  }
  if (userCfg.whisper_language && cfg.whisper_languages && cfg.whisper_languages[userCfg.whisper_language]) {
    cfg.whisper_language = userCfg.whisper_language;
  }
  return cfg;
}

// Migrasi satu arah otomatis dari plaintext localStorage ke HTTPOnly Secure cookies terenkripsi
async function migrateLegacyLocalStorage() {
  try {
    const rawAi = localStorage.getItem(AI_STORAGE_KEY);
    if (rawAi) {
      const parsed = JSON.parse(rawAi);
      if (parsed && parsed.providers) {
        for (const [pName, pData] of Object.entries(parsed.providers)) {
          if (pData?.key || pData?.model) {
            await api("/api/credentials/ai", {
              method: "POST",
              body: JSON.stringify({ provider: pName, key: pData.key || "", model: pData.model || "" }),
            }).catch(() => {});
          }
        }
      }
      localStorage.removeItem(AI_STORAGE_KEY);
    }
  } catch {}

  try {
    const rawMedia = localStorage.getItem(USER_MEDIA_KEY);
    if (rawMedia) {
      const parsed = JSON.parse(rawMedia);
      if (parsed) {
        if (parsed.host === "cloudinary" && parsed.cloudinary) {
          await api("/api/credentials/media", {
            method: "POST",
            body: JSON.stringify({ host: "cloudinary", credentials: parsed.cloudinary }),
          }).catch(() => {});
        } else if (parsed.host === "r2" && parsed.r2) {
          await api("/api/credentials/media", {
            method: "POST",
            body: JSON.stringify({ host: "r2", credentials: parsed.r2 }),
          }).catch(() => {});
        }
      }
      localStorage.removeItem(USER_MEDIA_KEY);
    }
  } catch {}

  try {
    localStorage.removeItem(USER_TOKEN_KEY);
  } catch {}
}

const STATUS_LABEL = {
  queued: "Menunggu antrean...", downloading: "Mengunduh", preparing: "Menyiapkan", analyzing: "Analisis AI",
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
  const token = getStoredToken();
  const headers = {
    ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    ...(opts.headers || {}),
  };
  if (token && !headers["Authorization"] && !headers["authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
    headers["X-Auth-Token"] = token;
  }
  const res = await fetch(path, {
    credentials: "same-origin",
    ...opts,
    headers,
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
      if (ev.job.id === state.current && ev.job.status === "error" && state.jobs[ev.job.id]?.status !== "error") {
        toast(`Gagal: ${ev.job.error}`, true);
      }
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
    card.innerHTML = `<h2><svg class="icon icon-brand" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg> Pemakaian AI</h2><p class="muted small">Tidak tercatat: proyek ini dianalisis sebelum fitur pencatatan token ditambahkan.</p>`;
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
    <div class="row between"><h2><svg class="icon icon-brand" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg> Pemakaian AI</h2><span class="muted small">${esc(models)} · ${entries.length} panggilan</span></div>
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
  setView("#view-usage");
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
      const e = await api(`/api/estimate?${q}`, { headers: aiHeaders() });
      const money = e.tier === "free" ? "gratis (tier Free)" : e.usd == null ? "harga model belum diatur" : `≈ ${fmtMoney(e.usd)}`;
      box.innerHTML = `<svg class="icon icon-brand" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg> Perkiraan pemakaian AI (${esc(e.provider_label || "")} · ${esc(e.model)}): ~${fmtTokens(e.prompt_tokens)} token input + ~${fmtTokens(e.output_tokens)} output → <b>${money}</b>` +
        (e.low_res ? ` <span class="muted">· video &gt; 20 menit dianalisis resolusi rendah</span>` : "");
      box.hidden = false;
    } catch {
      box.hidden = true;
    }
  }, 250);
}
["#in-num", "#in-max", "#in-subs"].forEach((sel) => $(sel).addEventListener("input", updateEstimate));

// Format Cepat (Presets)
const PRESETS = {
  tiktok: {
    name: "TikTok / Reels / Shorts",
    aspect: "9:16",
    layout: "face",
    min_len: 30,
    max_len: 60,
    subtitles: true,
    remove_silence: true,
    show_title: true,
    detail: "9:16 · Fokus wajah · Subtitle ON · Hapus jeda ON",
  },
  podcast: {
    name: "Podcast Highlight",
    aspect: "9:16",
    layout: "face",
    min_len: 45,
    max_len: 90,
    subtitles: true,
    remove_silence: true,
    show_title: true,
    detail: "9:16 · Wajah + judul · Hapus jeda ON · 45–90 dtk",
  },
  square: {
    name: "Feed Persegi",
    aspect: "1:1",
    layout: "crop",
    min_len: 30,
    max_len: 60,
    subtitles: true,
    remove_silence: true,
    show_title: true,
    detail: "1:1 · Crop tengah · Subtitle ON · 30–60 dtk",
  },
  youtube: {
    name: "YouTube Clip",
    aspect: "16:9",
    layout: "original",
    min_len: 60,
    max_len: 90,
    subtitles: true,
    remove_silence: false,
    show_title: true,
    detail: "16:9 · Landscape Asli · Subtitle ON · 60–90 dtk",
  },
};

function applyPreset(presetKey) {
  const p = PRESETS[presetKey];
  if (!p) return;
  document.querySelectorAll(".preset-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.preset === presetKey);
  });
  if ($("#in-aspect")) $("#in-aspect").value = p.aspect;
  if ($("#in-layout")) $("#in-layout").value = p.layout;
  if ($("#in-min")) $("#in-min").value = p.min_len;
  if ($("#in-max")) $("#in-max").value = p.max_len;
  if ($("#in-subs")) $("#in-subs").checked = p.subtitles;
  if ($("#in-trim")) $("#in-trim").checked = p.remove_silence;
  if ($("#in-title")) $("#in-title").checked = p.show_title;
  const lbl = $("#preset-active-label");
  if (lbl) lbl.textContent = p.name;
  const det = $("#preset-active-detail");
  if (det) det.textContent = p.detail;
  updateEstimate();
}

function checkActivePreset() {
  const aspect = $("#in-aspect")?.value;
  const layout = $("#in-layout")?.value;
  const min = Number($("#in-min")?.value);
  const max = Number($("#in-max")?.value);
  const subs = $("#in-subs")?.checked;
  const trim = $("#in-trim")?.checked;
  const title = $("#in-title")?.checked;

  let matchedKey = null;
  for (const [key, p] of Object.entries(PRESETS)) {
    if (p.aspect === aspect && p.layout === layout && p.min_len === min && p.max_len === max &&
        p.subtitles === subs && p.remove_silence === trim && p.show_title === title) {
      matchedKey = key;
      break;
    }
  }

  document.querySelectorAll(".preset-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.preset === matchedKey);
  });

  const lbl = $("#preset-active-label");
  const det = $("#preset-active-detail");
  if (matchedKey) {
    if (lbl) lbl.textContent = PRESETS[matchedKey].name;
    if (det) det.textContent = PRESETS[matchedKey].detail;
  } else {
    if (lbl) lbl.textContent = "Kustom";
    if (det) det.textContent = `${aspect} · ${LAYOUT_LABEL[layout] || layout} · ${min}–${max} dtk · Subtitle ${subs ? "ON" : "OFF"}`;
  }
}

document.querySelectorAll(".preset-card").forEach((card) => {
  card.addEventListener("click", () => applyPreset(card.dataset.preset));
});
["#in-aspect", "#in-layout", "#in-min", "#in-max", "#in-subs", "#in-trim", "#in-title"].forEach((sel) => {
  const el = $(sel);
  if (el) el.addEventListener("change", () => {
    checkActivePreset();
    updateEstimate();
  });
});

// ---------- Sidebar ----------
function renderJobList() {
  const query = state.searchQuery.trim().toLocaleLowerCase();
  const allJobs = Object.values(state.jobs);
  const jobs = allJobs
    .filter((j) => {
      const matchesQuery = !query || [j.name, j.id].some((value) =>
        String(value || "").toLocaleLowerCase().includes(query));
      const matchesStatus = state.activeFilter === "all"
        || (state.activeFilter === "ready" && j.status === "done")
        || (state.activeFilter === "running" && RUNNING.has(j.status));
      return matchesQuery && matchesStatus;
    })
    .sort((a, b) => b.created_at - a.created_at);
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
    : `<p class="muted small">${allJobs.length ? "Tidak ada proyek yang cocok dengan pencarian." : "Belum ada proyek."}</p>`;
}
$("#job-list").addEventListener("click", (e) => {
  const item = e.target.closest(".job-item");
  if (item) openJob(item.dataset.id);
});
$("#search-job").addEventListener("input", (e) => {
  state.searchQuery = e.target.value;
  renderJobList();
});
document.querySelectorAll(".btn-filter").forEach((button) => {
  button.addEventListener("click", () => {
    state.activeFilter = button.dataset.status;
    document.querySelectorAll(".btn-filter").forEach((item) =>
      item.classList.toggle("active", item === button));
    renderJobList();
  });
});

// ---------- Form proyek baru ----------
function showNew() {
  state.current = null;
  setView("#view-new");
  $("#src-video").removeAttribute("src");
  renderJobList();
}
$("#btn-new").onclick = showNew;

document.querySelectorAll("#view-new .tab").forEach((tab) => {
  tab.onclick = () => {
    state.src = tab.dataset.src;
    updateEstimate();
    document.querySelectorAll("#view-new .tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll("[data-src-pane]").forEach((p) => (p.hidden = p.dataset.srcPane !== state.src));
  };
});

function setFile(file) {
  if (file) {
    const maxMb = state.config?.max_filesize_mb || 500;
    const maxBytes = maxMb * 1024 * 1024;
    if (file.size > maxBytes) {
      toast(`Ukuran file (${(file.size / 1e6).toFixed(1)} MB) melebihi batas maksimum ${maxMb} MB.`, true);
      $("#in-file").value = "";
      state.file = null;
      $("#drop-label").textContent = "Tarik video ke sini atau klik untuk memilih";
      return;
    }
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    const allowed = [".mp4", ".mov", ".m4v", ".webm", ".mkv"];
    if (!allowed.includes(ext)) {
      toast(`Format file '${ext}' tidak didukung. Pilih video MP4, MOV, WEBM, atau MKV.`, true);
      $("#in-file").value = "";
      state.file = null;
      $("#drop-label").textContent = "Tarik video ke sini atau klik untuk memilih";
      return;
    }
  }
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
    toast(`Isi API key ${state.config?.providers?.[state.config.provider]?.label || "AI"} dulu di Pengaturan.`, true);
    showSettings();
    return;
  }
  const fd = new FormData();
  if (state.src === "file") {
    if (!state.file) return toast("Pilih file video dulu.", true);
    const maxMb = state.config?.max_filesize_mb || 500;
    if (state.file.size > maxMb * 1024 * 1024) {
      return toast(`Ukuran file melebihi batas maksimum ${maxMb} MB.`, true);
    }
    fd.append("file", state.file);
  } else {
    const url = $("#in-url").value.trim();
    if (!url) return toast("Masukkan link video.", true);
    if (!url.startsWith("https://")) {
      return toast("Hanya URL dengan protokol https:// yang diizinkan.", true);
    }
    fd.append("url", url);
  }
  const customMedia = userHasCustomMedia();
  const retHours = customMedia ? (state.config?.custom_retention_hours || 24) : (state.config?.server_retention_hours || 8);
  fd.append("options", JSON.stringify({
    num_clips: +$("#in-num").value, min_len: +$("#in-min").value, max_len: +$("#in-max").value,
    aspect: $("#in-aspect").value, layout: $("#in-layout").value,
    subtitles: $("#in-subs").checked, remove_silence: $("#in-trim").checked,
    show_title: $("#in-title").checked, instructions: $("#in-instr").value,
    logo_id: logoOptionToOption($("#in-logo").value),
    intro_id: logoOptionToOption($("#in-intro").value),
    outro_id: logoOptionToOption($("#in-outro").value),
    channels: state.newTargets || [],
    has_custom_media: customMedia,
    retention_hours: retHours,
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
    const data = JSON.parse(xhr.responseText || "{}");
    if (xhr.status >= 400) {
      const err = data.detail || "Gagal membuat proyek";
      $("#form-msg").textContent = err;
      $("#form-msg").className = "small err";
      return toast(err, true);
    }
    $("#form-msg").textContent = "";
    $("#form-msg").className = "muted small";
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
  xhr.withCredentials = true;
  Object.entries(aiHeaders()).forEach(([name, value]) => xhr.setRequestHeader(name, value));
  const jobToken = getStoredToken();
  if (jobToken) {
    xhr.setRequestHeader("Authorization", `Bearer ${jobToken}`);
    xhr.setRequestHeader("X-Auth-Token", jobToken);
  }
  xhr.send(fd);
};

// ---------- Detail proyek ----------
function openJob(id) {
  state.current = id;
  setView("#view-job");
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
  $("#job-stage").textContent = job.status === "error" ? `Gagal: ${job.error}` : (job.stage || (job.status === "queued" ? "Menunggu antrean..." : ""));
  $("#job-pct").textContent = indeterminate || job.status === "queued" ? "…" : `${Math.round(pct * 100)}%`;
  $("#job-bar").style.width = (indeterminate ? 100 : pct * 100) + "%";
  $("#job-bar").style.opacity = indeterminate ? "1" : "1";
  $("#job-bar").classList.toggle("analyzing", indeterminate);
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
    o.logo_id === "" ? "tanpa logo" : null,
    o.intro_id === "" ? "tanpa pembuka" : null,
    (o.channels || []).length ? `${o.channels.length} tujuan posting` : null,
  ].filter(Boolean).join("  ·  ");
  renderStatus(job);
  renderLog(job);

  const sum = $("#job-summary");
  sum.hidden = !job.summary;
  if (job.summary) sum.innerHTML = `<h2>Ringkasan AI</h2><p class="muted">${esc(job.summary)}</p>`;

  const custom = Boolean(job.has_custom_media || (job.retention_hours && job.retention_hours > 8));
  const retHours = job.retention_hours || (custom ? 24 : 8);
  const hostLabel = custom ? "Hosting Pribadi" : "Server Default";
  let retMsg = `Klip Anda akan disimpan selama ${retHours} jam (${hostLabel}). Segera unduh hasil klip Anda.`;
  if (job.created_at) {
    const expiresAt = job.created_at + retHours * 3600;
    const remainingSec = expiresAt - Date.now() / 1000;
    if (remainingSec > 0) {
      const remainingHours = Math.floor(remainingSec / 3600);
      const remainingMins = Math.floor((remainingSec % 3600) / 60);
      const timeLeftStr = remainingHours > 0 ? `${remainingHours} jam ${remainingMins} menit` : `${remainingMins} menit`;
      retMsg = `Klip Anda akan disimpan selama ${retHours} jam (${hostLabel}, sisa waktu: ~${timeLeftStr}). Segera unduh hasil klip Anda.`;
    } else {
      retMsg = `Masa simpan klip (${retHours} jam - ${hostLabel}) telah terlewati. Klip dapat dibersihkan sewaktu-waktu.`;
    }
  }
  const retWarn = $("#job-retention-msg");
  if (retWarn) retWarn.textContent = retMsg;

  renderJobUsage(job);

  const fmtCard = $("#job-format");
  fmtCard.hidden = !job.clips.length;
  if (fmtCard.dataset.job !== job.id) {
    fmtCard.dataset.job = job.id;
    $("#fmt-aspect").value = o.aspect;
    $("#fmt-layout").value = o.layout;
    $("#fmt-subs").checked = o.subtitles;
    fillLogoSelect($("#fmt-logo"), logoOptionValue(o.logo_id));
    fillBumperSelect($("#fmt-intro"), "intro", logoOptionValue(o.intro_id));
    fillBumperSelect($("#fmt-outro"), "outro", logoOptionValue(o.outro_id));
    state.fmtLogoWanted = logoOptionValue(o.logo_id);
    state.jobTargets = [...(o.channels || [])];
    $("#fmt-target-count").textContent = targetSummary(state.jobTargets);
    const box = $("#fmt-targets");
    delete box.dataset.loaded;
    box.innerHTML = "";
    $("#fmt-targets").parentElement.open = false;
    $("#fmt-trim").checked = !!o.remove_silence;
    $("#fmt-title").checked = !!o.show_title;
  }
  $("#btn-rerender-all").disabled = job.clips.some((c) => c.status === "queued" || c.status === "rendering");
  const readyCount = job.clips.filter((c) => c.status === "ready").length;
  const downloadAll = $("#btn-dl-all");
  downloadAll.hidden = readyCount === 0;
  downloadAll.href = `/api/jobs/${job.id}/download-all`;

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

// ---------- Kartu klip ringkas & Studio Layar Penuh ----------
function clipTextPreview(clip) {
  const cues = (clip.captions && clip.captions.length ? clip.captions : (clip.ai_captions || []));
  if (cues && cues.length) {
    return cues.map((c) => c.text).filter(Boolean).join(" ");
  }
  if (clip.hook) return clip.hook;
  return clip.reason || "Teks subtitle disiapkan otomatis dari transkrip saat klip dianalisis.";
}

let currentFsClipId = null;

function renderClips(job) {
  const wrap = $("#clips");
  const ids = new Set(job.clips.map((c) => c.id));
  [...wrap.children].forEach((el) => !ids.has(el.dataset.id) && el.remove());
  const sorted = [...job.clips].sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.start - b.start);
  sorted.forEach((clip, i) => {
    let card = wrap.querySelector(`[data-id="${clip.id}"]`);
    if (!card) {
      card = document.createElement("div");
      card.className = "clip-compact";
      card.dataset.id = clip.id;
      card.innerHTML = `
        <div class="clip-preview-thumb" data-act="open-fs" title="Klik untuk membuka Studio Layar Penuh">
          <div class="thumb-badges">
            <span class="badge-aspect">${job.options.aspect || "9:16"}</span>
            <span class="badge-duration dur"></span>
            <span class="badge-score score" hidden></span>
          </div>
          <div class="thumb-status"></div>
          <button type="button" class="btn-open-fs" data-act="open-fs">
            <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"/></svg> Buka Studio
          </button>
        </div>
        <div class="clip-compact-body">
          <div class="row between" style="align-items:flex-start;">
            <h4 class="clip-compact-title" title=""></h4>
          </div>
          <div class="clip-compact-hook"></div>
          <div class="clip-compact-text-preview" title="Teks narasi / subtitle awal">
            <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            <span class="text-snippet"></span>
          </div>
          <div class="pubstate" hidden></div>
          <div class="clip-compact-actions">
            <button type="button" class="btn-sm btn-primary" data-act="open-fs">Buka Studio</button>
            <button type="button" class="btn-sm" data-act="load" title="Buka di timeline editor sumber">
              <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg> Edit
            </button>
            <div class="more-menu-wrap">
              <button type="button" class="btn-sm btn-more" aria-label="Menu Opsi">•••</button>
              <div class="more-dropdown" hidden>
                <button type="button" class="more-item" data-act="copy">
                  <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg> Salin Caption
                </button>
                <button type="button" class="more-item" data-act="publish">
                  <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg> Post ke Buffer
                </button>
                <a class="more-item dl-mp4" download hidden>Unduh MP4</a>
                <a class="more-item dl-srt" download hidden>Unduh SRT</a>
                <a class="more-item dl-vtt" download hidden>Unduh VTT</a>
                <button type="button" class="more-item" data-act="rerender">Render Ulang</button>
                <button type="button" class="more-item danger" data-act="delete">
                  <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg> Hapus Klip
                </button>
              </div>
            </div>
          </div>
        </div>`;
    }
    if (wrap.children[i] !== card) wrap.insertBefore(card, wrap.children[i] || null);
    updateCard(job, clip, card);
  });

  if (currentFsClipId) {
    const dlg = $("#dlg-clip-fullscreen");
    if (dlg && dlg.open) {
      const idx = sorted.findIndex((c) => c.id === currentFsClipId);
      if (idx !== -1) {
        renderFullscreenModal(job, sorted, idx);
      }
    }
  }
}

function updateCard(job, clip, card) {
  const titleEl = $(".clip-compact-title", card);
  if (titleEl) {
    titleEl.textContent = clip.title;
    titleEl.title = clip.title;
  }
  const score = $(".score", card);
  if (score) {
    score.hidden = clip.score == null;
    score.textContent = `${clip.score}% Skor`;
  }
  const hookEl = $(".clip-compact-hook", card);
  if (hookEl) {
    hookEl.textContent = clip.hook ? `“${clip.hook}”` : "";
    hookEl.hidden = !clip.hook;
  }
  const snippet = $(".text-snippet", card);
  if (snippet) {
    snippet.textContent = clipTextPreview(clip);
  }
  const span = clip.end - clip.start;
  const out = clip.duration_out;
  const durText = out && out < span - 0.2 ? `${span.toFixed(1)} → ${out.toFixed(1)}s` : `${span.toFixed(1)}s`;
  const durEl = $(".dur", card);
  if (durEl) {
    durEl.textContent = durText;
    durEl.title = out && out < span - 0.2 ? "Durasi setelah jeda diam dibuang" : "";
  }

  const stat = $(".thumb-status", card);
  if (stat) {
    if (clip.status === "ready") {
      stat.textContent = "Siap";
      stat.className = "thumb-status";
    } else if (clip.status === "error") {
      stat.textContent = "Gagal";
      stat.className = "thumb-status run";
    } else {
      stat.textContent = clip.stage || "Menunggu antrean...";
      stat.className = "thumb-status queued";
    }
  }

  const busy = clip.status === "queued" || clip.status === "rendering";
  card.querySelectorAll("button[data-act=rerender], button[data-act=delete]").forEach((b) => (b.disabled = busy));
  const posting = ["uploading", "posting"].includes(clip.publish?.status);
  const btnPub = $("button[data-act=publish]", card);
  if (btnPub) btnPub.disabled = clip.status !== "ready" || posting;

  const dlMp4 = $(".dl-mp4", card);
  if (dlMp4) {
    dlMp4.hidden = clip.status !== "ready" || !clip.file;
    if (clip.file) dlMp4.href = `/media/${job.id}/${clip.file}?download=1`;
  }
  const dlSrt = $(".dl-srt", card);
  if (dlSrt) {
    dlSrt.hidden = !clip.srt;
    if (clip.srt) dlSrt.href = `/media/${job.id}/${clip.srt}?download=1`;
  }
  const dlVtt = $(".dl-vtt", card);
  if (dlVtt) {
    dlVtt.hidden = !clip.vtt;
    if (clip.vtt) dlVtt.href = `/media/${job.id}/${clip.vtt}?download=1`;
  }
  renderPublishState(job, clip, card);
}

function openFullscreenClip(clipId) {
  const job = state.jobs[state.current];
  if (!job || !job.clips) return;
  const sorted = [...job.clips].sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.start - b.start);
  const index = sorted.findIndex((c) => c.id === clipId);
  if (index === -1) return;
  currentFsClipId = clipId;
  renderFullscreenModal(job, sorted, index);
  const dlg = $("#dlg-clip-fullscreen");
  if (!dlg.open) dlg.showModal();
}

function renderFullscreenModal(job, sortedClips, index) {
  const clip = sortedClips[index];
  if (!clip) return;
  const total = sortedClips.length;

  // Header
  $("#fs-clip-index").textContent = `Klip ${index + 1} dari ${total}`;
  const statusEl = $("#fs-clip-status");
  if (clip.status === "ready") {
    statusEl.innerHTML = `<svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Siap Ditonton`;
    statusEl.className = "fs-badge";
    statusEl.style.background = "rgba(47, 191, 113, 0.15)";
    statusEl.style.color = "var(--ok)";
  } else if (clip.status === "error") {
    statusEl.innerHTML = `<svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Gagal`;
    statusEl.className = "fs-badge";
    statusEl.style.background = "rgba(235, 87, 87, 0.15)";
    statusEl.style.color = "var(--err)";
  } else {
    statusEl.textContent = clip.stage || "Memproses klip...";
    statusEl.className = "fs-badge";
    statusEl.style.background = "rgba(242, 153, 74, 0.15)";
    statusEl.style.color = "var(--warn)";
  }

  $("#btn-fs-prev").disabled = index === 0;
  $("#btn-fs-next").disabled = index === total - 1;

  // Phone Frame Aspect Ratio Simulator
  const phoneFrame = $("#fs-phone-frame");
  const aspect = job.options.aspect || "9:16";
  if (aspect === "1:1") {
    phoneFrame.style.aspectRatio = "1 / 1";
    phoneFrame.style.maxWidth = "360px";
  } else if (aspect === "16:9") {
    phoneFrame.style.aspectRatio = "16 / 9";
    phoneFrame.style.maxWidth = "400px";
  } else {
    phoneFrame.style.aspectRatio = "9 / 16";
    phoneFrame.style.maxWidth = "320px";
  }

  // Video Element
  const video = $("#fs-video-player");
  if (clip.status === "ready" && clip.file) {
    const src = `/media/${job.id}/${clip.file}?v=${clip.version}`;
    if (video.dataset.src !== src) {
      video.dataset.src = src;
      video.src = src;
    }
  } else {
    video.removeAttribute("src");
    delete video.dataset.src;
  }

  // Hook & Tags Overlay
  $("#fs-hook-text").textContent = clip.hook ? `“${clip.hook}”` : "";
  const tagsText = (clip.hashtags || []).map((t) => (t.startsWith("#") ? t : `#${t}`)).join(" ");
  $("#fs-tags-text").textContent = tagsText;

  // Metadata
  $("#fs-title").textContent = clip.title;
  const scoreEl = $("#fs-score");
  if (clip.score != null) {
    scoreEl.textContent = `${clip.score}% Skor`;
    scoreEl.hidden = false;
  } else {
    scoreEl.hidden = true;
  }

  const span = clip.end - clip.start;
  const out = clip.duration_out;
  $("#fs-duration").textContent = `${out && out < span - 0.2 ? `${out.toFixed(1)} dtk (jeda diam dibuang)` : `${span.toFixed(1)} dtk`}`;
  $("#fs-aspect").textContent = `${aspect} (${LAYOUT_LABEL[job.options.layout] || job.options.layout})`;
  $("#fs-reason").textContent = clip.reason || clip.hook || "";

  // Transcript / Subtitle List
  const cues = (clip.captions && clip.captions.length ? clip.captions : (clip.ai_captions || []));
  $("#fs-sub-count").textContent = cues && cues.length ? `${cues.length} baris subtitle` : "Belum ada subtitle";
  const transBox = $("#fs-transcript-list");
  transBox.innerHTML = "";
  if (cues && cues.length) {
    cues.forEach((c) => {
      const line = document.createElement("div");
      line.className = "fs-transcript-line";
      line.style.cursor = "pointer";
      line.title = "Klik untuk melompat ke waktu ini";
      line.innerHTML = `<span class="fs-sub-time">${fmt(c.start)}</span><span class="fs-sub-text">${esc(c.text)}</span>`;
      line.onclick = () => {
        if (video && !isNaN(video.duration)) {
          video.currentTime = Math.max(0, c.start);
          video.play().catch(() => {});
        }
      };
      transBox.appendChild(line);
    });
  } else {
    transBox.innerHTML = `<p class="muted small" style="margin: 8px 0;">Subtitle dan teks diselaraskan otomatis saat proses transkripsi Whisper/AI selesai.</p>`;
  }

  // Primary Actions
  const btnPub = $("#btn-fs-publish");
  btnPub.disabled = clip.status !== "ready";
  btnPub.onclick = () => openPublish(job, clip);

  const dlMp4 = $("#btn-fs-download-mp4");
  if (clip.status === "ready" && clip.file) {
    dlMp4.hidden = false;
    dlMp4.href = `/media/${job.id}/${clip.file}?download=1`;
  } else {
    dlMp4.hidden = true;
  }

  // Secondary Actions
  const dlSrt = $("#btn-fs-download-srt");
  if (clip.srt) {
    dlSrt.hidden = false;
    dlSrt.href = `/media/${job.id}/${clip.srt}?download=1`;
  } else {
    dlSrt.hidden = true;
  }

  const dlVtt = $("#btn-fs-download-vtt");
  if (clip.vtt) {
    dlVtt.hidden = false;
    dlVtt.href = `/media/${job.id}/${clip.vtt}?download=1`;
  } else {
    dlVtt.hidden = true;
  }

  $("#btn-fs-copy-caption").onclick = async () => {
    const text = cues && cues.length ? cues.map((c) => c.text).join(" ") : "";
    const parts = [clip.title, clip.hook ? `“${clip.hook}”` : "", text, tagsText].filter(Boolean);
    await navigator.clipboard.writeText(parts.join("\n\n"));
    toast("Caption & teks klip berhasil disalin!");
  };

  $("#btn-fs-edit-src").onclick = () => {
    $("#dlg-clip-fullscreen").close();
    $("#man-start").value = fmt(clip.start);
    $("#man-end").value = fmt(clip.end);
    $("#man-title").value = clip.title;
    const v = $("#src-video");
    v.currentTime = clip.start;
    renderTimeline();
    $("#editor").scrollIntoView({ behavior: "smooth" });
  };

  $("#btn-fs-rerender").disabled = clip.status === "queued" || clip.status === "rendering";
  $("#btn-fs-rerender").onclick = async () => {
    try {
      await api(`/api/jobs/${job.id}/clips/${clip.id}`, {
        method: "PATCH",
        body: JSON.stringify({ start: clip.start, end: clip.end, title: clip.title }),
      });
      toast("Render ulang klip dimulai.");
    } catch (err) {
      toast(err.message, true);
    }
  };

  $("#btn-fs-delete").disabled = clip.status === "queued" || clip.status === "rendering";
  $("#btn-fs-delete").onclick = async () => {
    if (!confirm(`Hapus klip “${clip.title}”?`)) return;
    try {
      await api(`/api/jobs/${job.id}/clips/${clip.id}`, { method: "DELETE" });
      $("#dlg-clip-fullscreen").close();
      toast("Klip dihapus.");
    } catch (err) {
      toast(err.message, true);
    }
  };

  $("#btn-fs-prev").onclick = () => {
    if (index > 0) openFullscreenClip(sortedClips[index - 1].id);
  };
  $("#btn-fs-next").onclick = () => {
    if (index < total - 1) openFullscreenClip(sortedClips[index + 1].id);
  };
}

$("#btn-fs-close").onclick = () => {
  const dlg = $("#dlg-clip-fullscreen");
  dlg.close();
  $("#fs-video-player")?.pause();
};
$("#dlg-clip-fullscreen").addEventListener("close", () => {
  $("#fs-video-player")?.pause();
  currentFsClipId = null;
});

const SERVICE_LABEL = { instagram: "Instagram", tiktok: "TikTok", youtube: "YouTube", facebook: "Facebook",
  linkedin: "LinkedIn", twitter: "X", threads: "Threads", bluesky: "Bluesky", mastodon: "Mastodon",
  pinterest: "Pinterest", googlebusiness: "Google Business" };
const POST_STATUS = { scheduled: "terjadwal", sending: "sedang dikirim", sent: "terkirim", error: "gagal",
  draft: "draf", needs_approval: "menunggu persetujuan" };

function pubMulti(state) {
  return new Set((state.results || []).map((r) => r.account_id)).size > 1;
}

function renderPublishState(job, clip, card) {
  const box = $(".pubstate", card);
  const pub = clip.publish;
  box.hidden = !pub;
  if (!pub) return;
  let head = "";
  if (pub.status === "uploading") head = `Mengunggah video… ${Math.round((pub.progress || 0) * 100)}%`;
  else if (pub.status === "posting") head = "Mengirim ke Buffer…";
  else if (pub.status === "error" && !pub.results.length) head = `<span class="bad">Gagal: ${esc(pub.error)}</span>`;
  else head = `Posting · <button type="button" class="ghost small-btn" data-act="pubrefresh">Cek status</button>`;
  const when = (iso) => (iso ? new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "");
  const rows = pub.results.map((r) => {
    const name = `${SERVICE_LABEL[r.service] || r.service} · ${esc(r.channel)}`
      + (r.account && pubMulti(pub) ? ` <span class="muted">(${esc(r.account)})</span>` : "");
    if (!r.ok) return `<div class="bad">Gagal ${name}: ${esc(r.error)}</div>`;
    const status = POST_STATUS[r.status] || r.status || "terkirim";
    const extra = r.error ? ` — ${esc(r.error)}` : r.link ? ` — <a href="${esc(r.link)}" target="_blank" rel="noopener">lihat</a>` : r.due_at && r.status === "scheduled" ? ` ${when(r.due_at)}` : "";
    return `<div class="${r.status === "error" ? "bad" : "ok"}">${name}: ${status}${extra}</div>`;
  });
  box.innerHTML = `<div>${head}</div>${rows.join("")}`;
}

// ---------- Pemilih channel tujuan (dipakai form proyek baru, kartu format, dan dialog posting) ----------
function channelRow(c, checked) {
  const off = c.isDisconnected || c.isLocked || !c.supportsVideo;
  const why = c.isDisconnected ? "terputus" : c.isLocked ? "terkunci" : !c.supportsVideo ? "tidak mendukung video" : "";
  return `<label class="channel ${off ? "off" : ""}">
    <input type="checkbox" value="${esc(c.key)}" ${off ? "disabled" : ""} ${!off && checked ? "checked" : ""} />
    ${c.avatar ? `<img src="${esc(c.avatar)}" alt="" referrerpolicy="no-referrer" />` : ""}
    <span>${esc(c.displayName || c.name)}</span>
    <span class="svc">${SERVICE_LABEL[c.service] || esc(c.service)}${why ? ` · ${why}` : ""}</span>
  </label>`;
}

function renderChannels(box, channels, accounts, errors, selected) {
  if (!channels.length) {
    box.innerHTML = `<p class="muted small">Belum ada channel di Buffer. Hubungkan akun sosial media di publish.buffer.com.</p>`;
    return;
  }
  const multi = (accounts || []).length > 1;
  const groups = multi
    ? accounts.map((a) => {
        const own = channels.filter((c) => c.account_id === a.id);
        return own.length ? `<div class="channel-group">${esc(a.label)}</div>`
          + own.map((c) => channelRow(c, selected.includes(c.key))).join("") : "";
      }).join("")
    : channels.map((c) => channelRow(c, selected.includes(c.key))).join("");
  box.innerHTML = (errors || []).map((e) => `<p class="err">${esc(e)}</p>`).join("") + groups;
}

async function loadChannelsInto(box, selected, refresh = false) {
  box.innerHTML = `<p class="muted small">Memuat channel…</p>`;
  try {
    const data = await api(`/api/buffer/channels${refresh ? "?refresh=true" : ""}`);
    state.channels = data;
    renderChannels(box, data.channels, data.accounts, data.errors, selected || []);
    return data;
  } catch (err) {
    box.innerHTML = `<p class="err">${esc(err.message)}</p>`;
    return null;
  }
}

function checkedChannels(box) {
  return [...box.querySelectorAll("input:checked")].map((i) => i.value);
}

function targetSummary(keys) {
  if (!keys.length) return "(belum dipilih)";
  const names = keys.map((k) => state.channels?.channels?.find((c) => c.key === k))
    .map((c, i) => (c ? c.displayName || c.name : keys[i]));
  return `· ${names.length} channel: ${names.join(", ")}`;
}

// Channel hanya diambil saat bagiannya dibuka, supaya kuota Buffer tidak terpakai sia-sia.
function wireTargets(details, box, countEl, getSelected, onChange) {
  details.addEventListener("toggle", async () => {
    if (!details.open || box.dataset.loaded) return;
    box.dataset.loaded = "1";
    await loadChannelsInto(box, getSelected());
    countEl.textContent = targetSummary(getSelected());
  });
  box.addEventListener("change", () => {
    const keys = checkedChannels(box);
    countEl.textContent = targetSummary(keys);
    onChange?.(keys);
  });
}

wireTargets($("#new-targets").parentElement, $("#new-targets"), $("#new-target-count"), () => state.newTargets || [],
            (keys) => (state.newTargets = keys));
wireTargets($("#fmt-targets").parentElement, $("#fmt-targets"), $("#fmt-target-count"), () => state.jobTargets || [],
            (keys) => (state.jobTargets = keys));

// ---------- Posting via Buffer ----------
const pub = { job: null, clip: null, channels: [] };

function clipCaption(clip) {
  const tags = (clip.hashtags || []).map((t) => (t.startsWith("#") ? t : `#${t}`)).join(" ");
  return [clip.title, clip.hook, tags].filter(Boolean).join("\n\n");
}

async function loadChannels(refresh = false) {
  const box = $("#pub-channels");
  let remembered = [];
  try { remembered = JSON.parse(localStorage.getItem("pubChannels") || "[]"); } catch {}
  // Tujuan yang dipilih sebelum render dipakai lebih dulu; kalau kosong, pakai pilihan terakhir.
  const selected = pub.job?.options?.channels?.length ? pub.job.options.channels : remembered;
  const data = await loadChannelsInto(box, selected, refresh);
  if (data) {
    pub.channels = data.channels;
    pub.multiAccount = (data.accounts || []).length > 1;
  }
  updateCount();
}

function updateCount() {
  const n = $("#pub-text").value.length;
  const selected = [...$("#pub-channels").querySelectorAll("input:checked")].map((i) => pub.channels.find((c) => c.key === i.value));
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
  const names = ids.map((id) => pub.channels.find((c) => c.key === id))
    .map((c) => `${c.displayName || c.name}${pub.multiAccount ? ` (${c.account})` : ""}`).join(", ");
  const verb = mode === "shareNow" ? "langsung dipublikasikan" : "dijadwalkan";
  if (!confirm(`Klip akan ${verb} ke: ${names}. Lanjutkan?`)) return;
  const btn = $("#btn-pub-send");
  btn.disabled = true;
  try {
    const activeMedia = getActiveMediaContext();
    await api(`/api/jobs/${pub.job.id}/clips/${pub.clip.id}/publish`, {
      method: "POST",
      body: JSON.stringify({
        channel_ids: ids,
        text: $("#pub-text").value,
        mode,
        due_at,
        media_host: activeMedia.provider,
        media_credentials: activeMedia.credentials,
      }),
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
  const stat = $(".thumb-status", card);
  if (stat) {
    stat.textContent = stage || `${Math.round(p * 100)}%`;
    stat.className = "thumb-status run";
  }
  const lbl = $(".overlay .lbl", card);
  if (lbl && stage) lbl.textContent = stage;
  const bar = $(".overlay .bar > div", card);
  if (bar) bar.style.width = p * 100 + "%";
  const pct = $(".overlay .pct", card);
  if (pct) pct.textContent = `${Math.round(p * 100)}%`;
  const job = state.jobs[state.current];
  if (job?.status === "rendering") renderStatus(job);
}

// Menu Dropdown More ("...")
document.addEventListener("click", (e) => {
  const btnMore = e.target.closest(".btn-more");
  if (btnMore) {
    const wrap = btnMore.closest(".more-menu-wrap");
    const menu = wrap ? wrap.querySelector(".more-dropdown") : null;
    if (menu) {
      const isHidden = menu.hidden;
      document.querySelectorAll(".more-dropdown").forEach((m) => (m.hidden = true));
      menu.hidden = !isHidden;
    }
    return;
  }
  if (!e.target.closest(".more-dropdown")) {
    document.querySelectorAll(".more-dropdown").forEach((m) => (m.hidden = true));
  }
});

$("#clips").addEventListener("click", async (e) => {
  const openFs = e.target.closest("[data-act=open-fs]");
  if (openFs) {
    const card = openFs.closest(".clip-compact") || openFs.closest(".clip");
    if (card) openFullscreenClip(card.dataset.id);
    return;
  }
  const btn = e.target.closest("button[data-act], a[data-act]");
  if (!btn) return;
  const card = btn.closest(".clip-compact") || btn.closest(".clip");
  if (!card) return;
  const job = state.jobs[state.current];
  if (!job) return;
  const clip = job.clips.find((c) => c.id === card.dataset.id);
  if (!clip) return;

  try {
    if (btn.dataset.act === "rerender") {
      await api(`/api/jobs/${job.id}/clips/${clip.id}`, {
        method: "PATCH",
        body: JSON.stringify({ start: clip.start, end: clip.end, title: clip.title }),
      });
      toast("Render ulang dimulai.");
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
      const text = clipTextPreview(clip);
      await navigator.clipboard.writeText([clip.title, clip.hook ? `“${clip.hook}”` : "", text, tags].filter(Boolean).join("\n\n"));
      toast("Caption & teks disalin.");
    } else if (btn.dataset.act === "publish") {
      openPublish(job, clip);
    } else if (btn.dataset.act === "pubrefresh") {
      await api(`/api/jobs/${job.id}/clips/${clip.id}/publish/refresh`, { method: "POST" });
      toast("Status posting diperbarui.");
    } else if (btn.dataset.act === "delete") {
      if (!confirm(`Hapus klip “${clip.title}”?`)) return;
      await api(`/api/jobs/${job.id}/clips/${clip.id}`, { method: "DELETE" });
      toast("Klip dihapus.");
    }
  } catch (err) {
    toast(err.message, true);
  }
});

// Pintasan Keyboard Studio
window.addEventListener("keydown", (e) => {
  const dlg = $("#dlg-clip-fullscreen");
  const isInput = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);

  if (dlg?.open) {
    if (e.key === "Escape") {
      dlg.close();
      $("#fs-video-player")?.pause();
      return;
    }
    if (isInput) return;
    if (e.code === "Space") {
      e.preventDefault();
      const video = $("#fs-video-player");
      if (video) {
        if (video.paused) video.play().catch(() => {});
        else video.pause();
      }
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      const video = $("#fs-video-player");
      if (video) video.currentTime = Math.max(0, video.currentTime - 5);
      return;
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const video = $("#fs-video-player");
      if (video) video.currentTime = Math.min(video.duration || 0, video.currentTime + 5);
      return;
    }
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
        logo_id: logoOptionToOption($("#fmt-logo").value),
        intro_id: logoOptionToOption($("#fmt-intro").value),
        outro_id: logoOptionToOption($("#fmt-outro").value),
        channels: state.jobTargets || [],
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
function updateRetentionUI() {
  const custom = userHasCustomMedia();
  const retHours = custom ? (state.config?.custom_retention_hours || 24) : (state.config?.server_retention_hours || 8);
  const hostLabel = custom ? "Hosting Pribadi (24 Jam)" : "Server Default (8 Jam)";
  const notice = $("#retention-new-notice");
  if (notice) {
    notice.innerHTML = `Klip Anda akan disimpan selama <strong>${retHours} jam</strong> (${hostLabel}). Segera unduh hasil klip Anda.`;
  }
}

async function loadConfig() {
  await Promise.all([loadAiCredentials(), loadMediaCredentials()]);
  state.config = applyStoredAi(await api("/api/config"));
  fillSettings();
  updateRetentionUI();
  if (!state.config.has_key) showSettings("ai");
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

const KEY_HELP = {
  gemini: 'Buat gratis di <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Google AI Studio</a>.',
  anthropic: 'Buat di <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">Anthropic Console</a>.',
  openai: 'Buat di <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">OpenAI Platform</a>.',
};
const PROVIDER_NOTE = {
  gemini: "Gemini menganalisis video secara langsung (gambar dan audio).",
  anthropic: "Claude menganalisis klip berdasarkan transkrip bertimestamp dan sampel frame visual.",
  openai: "ChatGPT menganalisis klip berdasarkan transkrip bertimestamp dan sampel frame visual.",
};

function currentProvider() {
  return $("#set-provider").value || state.config.provider;
}

function fillProviderFields() {
  const cfg = state.config;
  const name = currentProvider();
  const p = cfg.providers[name];
  $("#provider-note").textContent = PROVIDER_NOTE[name] || "";
  $("#set-key-label").textContent = `Ganti API Key (${p.label})`;
  $("#key-help").innerHTML = (KEY_HELP[name] || "") +
    " Disimpan secara privat dan aman di cookie browser (HTTPOnly, Secure, SameSite, terenkripsi AES-256) sehingga kebal terhadap pencurian skrip XSS.";
  const savedKeyInput = $("#set-key-saved");
  if (savedKeyInput) {
    if (p.has_key && p.key_hint) {
      savedKeyInput.value = `••••••••••••••••••••${p.key_hint} (Cookie HttpOnly)`;
    } else if (p.has_key) {
      savedKeyInput.value = `•••••••••••••••••••• (Cookie HttpOnly)`;
    } else {
      savedKeyInput.value = "Belum ada API key tersimpan";
    }
  }
  $("#set-key-hint").textContent = p.has_key
    ? "Key aktif tersimpan di cookie aman di atas. Kosongkan kolom 'Ganti API Key' jika tidak ingin mengubahnya."
    : "Belum ada key yang tersimpan. Masukkan API key baru di kolom 'Ganti API Key'.";
  const sel = $("#set-model");
  const modelToSet = isModelUnavailable(p.model) ? (p.default_model || "gemini-3.8-flash") : p.model;
  if (![...sel.options].some((o) => o.value === modelToSet) && !isModelUnavailable(modelToSet)) {
    sel.add(new Option(modelToSet, modelToSet));
  }
  sel.value = modelToSet;
}

function fillSettings() {
  const cfg = state.config;
  const psel = $("#set-provider");
  const keep = psel.dataset.dirty ? psel.value : cfg.provider;
  psel.innerHTML = "";
  for (const [name, p] of Object.entries(cfg.providers)) {
    psel.add(new Option(`${p.label}${p.has_key ? "" : " — belum ada API key"}`, name));
  }
  psel.value = keep;
  const sel = $("#set-model");
  const currentModel = isModelUnavailable(cfg.providers[keep].model)
    ? (cfg.providers[keep].default_model || "gemini-3.8-flash")
    : cfg.providers[keep].model;
  if (![...sel.options].some((o) => o.value === currentModel) && !isModelUnavailable(currentModel)) {
    sel.add(new Option(currentModel, currentModel));
  }
  setField(sel, currentModel);
  fillProviderFields();
  const wsel = $("#set-whisper");
  const wval = wsel.dataset.dirty ? wsel.value : cfg.whisper_model;
  wsel.innerHTML = "";
  for (const [name, desc] of Object.entries(cfg.whisper_models)) {
    wsel.add(new Option(`${cfg.whisper_downloaded[name] ? "[Siap] " : ""}${name} — ${desc}`, name));
  }
  wsel.value = wval;
  const lsel = $("#set-lang");
  const lval = lsel.dataset.dirty ? lsel.value : cfg.whisper_language;
  lsel.innerHTML = "";
  for (const [code, label] of Object.entries(cfg.whisper_languages)) lsel.add(new Option(label, code));
  lsel.value = lval;
  renderAccounts(cfg.buffer_accounts || []);
  const mc = state.mediaCredentials || { host: "default" };
  const hostSel = $("#set-host");
  if (hostSel && !hostSel.dataset.dirty) {
    hostSel.value = mc.host || "default";
  }
  showHostFields();
  fillMediaSettings();
  $("#set-info").textContent = `subtitle: ${cfg.subtitles_supported ? "didukung" : "tidak didukung"} · deteksi fokus: ${cfg.face_tracking ? "aktif" : "tidak tersedia"}`;
}

function fillMediaSettings() {
  const mc = state.mediaCredentials || { host: "default", configured: {}, fields: {} };
  const selHost = $("#set-host") ? $("#set-host").value : (mc.host || "default");

  // Isi data Cloudinary dari metadata server (tanpa mengekspos secret)
  const cFields = mc.fields?.cloudinary || {};
  document.querySelectorAll('[data-host="cloudinary"] [data-media-field]').forEach((inp) => {
    const field = inp.dataset.mediaField;
    if (!inp.dataset.dirty) {
      if (inp.type === "password") {
        inp.value = "";
        inp.placeholder = cFields.has_secret ? "Tersimpan di Cookie HttpOnly (••••••••)" : "API secret Cloudinary Anda";
      } else {
        inp.value = cFields[field] || "";
      }
    }
  });

  // Isi data R2 dari metadata server (tanpa mengekspos secret)
  const rFields = mc.fields?.r2 || {};
  document.querySelectorAll('[data-host="r2"] [data-media-field]').forEach((inp) => {
    const field = inp.dataset.mediaField;
    if (!inp.dataset.dirty) {
      if (inp.type === "password") {
        inp.value = "";
        inp.placeholder = rFields.has_secret ? "Tersimpan di Cookie HttpOnly (••••••••)" : "Secret Access Key R2";
      } else {
        inp.value = rFields[field] || "";
      }
    }
  });

  // Warning for missing fields or guidance
  const missing = $("#host-missing");
  if (missing) {
    if (selHost === "default") {
      if (state.config && !state.config.server_media_configured) {
        missing.hidden = false;
        missing.textContent = "Penyimpanan standar belum dikonfigurasi. Silakan gunakan Cloudinary atau R2 pribadi Anda di bawah untuk mengaktifkan fitur publikasi.";
      } else {
        missing.hidden = true;
      }
    } else {
      const requiredFields = selHost === "cloudinary"
        ? ["cloud_name", "api_key", "api_secret"]
        : ["account_id", "bucket", "access_key_id", "secret_access_key", "public_url"];
      const currentCreds = sm[selHost] || {};
      const missingKeys = requiredFields.filter((k) => !currentCreds[k] || !currentCreds[k].trim());
      if (missingKeys.length > 0) {
        missing.hidden = false;
        missing.textContent = `Kredensial belum lengkap: ${missingKeys.join(", ")}. Lengkapi dan simpan untuk retensi 24 jam.`;
      } else {
        missing.hidden = true;
      }
    }
  }
}

// ---------- Logo (pustaka) & penutup ----------
const LOGO_DEFAULT = "__default__";   // pakai logo default
const LOGO_NONE = "__none__";         // proyek ini tanpa logo

function logoOptionValue(logoId) {
  // Opsi proyek: null = default, "" = tanpa logo, selain itu id logo.
  return logoId === "" ? LOGO_NONE : logoId || LOGO_DEFAULT;
}

function logoOptionToOption(value) {
  if (value === LOGO_NONE) return "";
  return value === LOGO_DEFAULT ? null : value;
}

function fillLogoSelect(sel, value) {
  const logos = state.branding?.logos || [];
  const def = logos.find((l) => l.id === state.branding?.default_logo);
  sel.innerHTML = "";
  sel.add(new Option(def ? `Logo default (${def.label})` : "Tanpa logo (belum ada default)", LOGO_DEFAULT));
  for (const lg of logos) sel.add(new Option(lg.label, lg.id));
  sel.add(new Option("Tanpa logo", LOGO_NONE));
  sel.value = [...sel.options].some((o) => o.value === value) ? value : LOGO_DEFAULT;
}

function renderLogoLibrary() {
  const { logos = [], default_logo, positions = {} } = state.branding || {};
  const box = $("#logo-list");
  box.innerHTML = logos.length
    ? logos.map((lg) => `<div class="logo-row" data-id="${esc(lg.id)}">
        <div class="brand-preview small"><img src="${lg.url}?v=${lg.size_bytes}" alt="" /></div>
        <div class="grow">
          <div class="row wrap">
            <input class="grow logo-name" value="${esc(lg.label)}" data-field="label" />
            <label class="check inline"><input type="radio" name="logo-default" value="${esc(lg.id)}" ${lg.id === default_logo ? "checked" : ""} /> Default</label>
            <button type="button" class="ghost small-btn danger" data-logo="remove">Hapus</button>
          </div>
          <div class="row wrap small">
            <select data-field="position">${Object.entries(positions).map(([v, t]) => `<option value="${v}" ${v === lg.position ? "selected" : ""}>${t}</option>`).join("")}</select>
            <label class="inline-num">Lebar % <input type="number" data-field="size" min="3" max="40" step="1" value="${lg.size}" /></label>
            <label class="inline-num">Transparansi <input type="number" data-field="opacity" min="0.1" max="1" step="0.05" value="${lg.opacity}" /></label>
            <label class="inline-num">Tepi % <input type="number" data-field="margin" min="0" max="25" step="1" value="${lg.margin}" /></label>
          </div>
        </div>
      </div>`).join("")
    : `<p class="muted small">Belum ada logo. Tambahkan di bawah, lalu pilih logo mana yang dipakai tiap proyek.</p>`;
}

function fillBumperSelect(sel, role, value) {
  const list = state.branding?.bumpers || [];
  const def = list.find((b) => b.id === state.branding?.[`default_${role}`]);
  const label = role === "intro" ? "pembuka" : "penutup";
  sel.innerHTML = "";
  sel.add(new Option(def ? `Default: ${def.label}` : `Tanpa ${label}`, LOGO_DEFAULT));
  for (const b of list) sel.add(new Option(b.label, b.id));
  sel.add(new Option(`Tanpa ${label}`, LOGO_NONE));
  sel.value = [...sel.options].some((o) => o.value === value) ? value : LOGO_DEFAULT;
}

function renderBumperLibrary() {
  const { bumpers = [], default_intro, default_outro } = state.branding || {};
  $("#bumper-list").innerHTML = bumpers.length
    ? bumpers.map((b) => `<div class="logo-row" data-id="${esc(b.id)}">
        <div class="brand-preview small">${b.is_video
          ? `<video src="${b.url}?v=${b.size_bytes}#t=0.1" muted playsinline preload="metadata"></video>`
          : `<img src="${b.url}?v=${b.size_bytes}" alt="" />`}</div>
        <div class="grow">
          <div class="row wrap">
            <input class="grow bumper-name" value="${esc(b.label)}" data-field="label" />
            <button type="button" class="ghost small-btn danger" data-bumper="remove">Hapus</button>
          </div>
          <div class="row wrap small">
            <label class="check inline"><input type="checkbox" data-role="intro" ${b.id === default_intro ? "checked" : ""} /> Pembuka</label>
            <label class="check inline"><input type="checkbox" data-role="outro" ${b.id === default_outro ? "checked" : ""} /> Penutup</label>
            ${b.is_video
              ? `<label class="check inline"><input type="checkbox" data-field="keep_audio" ${b.keep_audio ? "checked" : ""} /> Pakai audionya</label>`
              : `<label class="inline-num">Durasi (dtk) <input type="number" data-field="duration" min="0.5" max="15" step="0.5" value="${b.duration}" /></label>`}
          </div>
        </div>
      </div>`).join("")
    : `<p class="muted small">Belum ada bumper. Tambahkan video/gambar pembuka atau penutup di bawah.</p>`;
}

function renderBranding(data) {
  state.branding = data;
  renderLogoLibrary();
  renderBumperLibrary();
  fillLogoSelect($("#in-logo"), $("#in-logo").value || LOGO_DEFAULT);
  fillBumperSelect($("#in-intro"), "intro", $("#in-intro").value || LOGO_DEFAULT);
  fillBumperSelect($("#in-outro"), "outro", $("#in-outro").value || LOGO_DEFAULT);
  const job = state.jobs[state.current];
  if (job) {
    fillLogoSelect($("#fmt-logo"), state.fmtLogoWanted || logoOptionValue(job.options.logo_id));
    fillBumperSelect($("#fmt-intro"), "intro", logoOptionValue(job.options.intro_id));
    fillBumperSelect($("#fmt-outro"), "outro", logoOptionValue(job.options.outro_id));
  }
}

async function loadBranding() {
  try {
    renderBranding(await api("/api/branding"));
  } catch (err) {
    console.warn(err);
  }
}

async function brandingCall(path, opts) {
  try {
    renderBranding(await api(path, opts));
    $("#brand-msg").textContent = "Tersimpan. Klip lama perlu Render ulang untuk ikut berubah.";
  } catch (err) {
    $("#brand-msg").textContent = err.message;
  }
}

$("#logo-list").addEventListener("change", (e) => {
  const row = e.target.closest(".logo-row");
  if (!row) return;
  if (e.target.name === "logo-default") {
    brandingCall("/api/branding/default-logo", { method: "POST", body: JSON.stringify({ logo_id: row.dataset.id }) });
    return;
  }
  const field = e.target.dataset.field;
  if (!field) return;
  const value = field === "label" || field === "position" ? e.target.value : Number(e.target.value);
  brandingCall(`/api/branding/logos/${row.dataset.id}`, { method: "PATCH", body: JSON.stringify({ [field]: value }) });
});

$("#logo-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-logo=remove]");
  if (!btn) return;
  const row = btn.closest(".logo-row");
  const name = $(".logo-name", row).value;
  if (!confirm(`Hapus logo “${name}”? Proyek yang memakainya akan kembali ke logo default.`)) return;
  brandingCall(`/api/branding/logos/${row.dataset.id}`, { method: "DELETE" });
});

$("#btn-add-logo").onclick = () => $("#logo-file").click();
$("#logo-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("label", $("#logo-label").value.trim());
  $("#brand-msg").textContent = `Mengunggah ${file.name}…`;
  try {
    const data = await api("/api/branding/logos", { method: "POST", body: fd });
    renderBranding(data);
    $("#logo-label").value = "";
    $("#brand-msg").textContent = `Logo “${data.added.label}” ditambahkan.`;
  } catch (err) {
    $("#brand-msg").textContent = err.message;
  } finally {
    e.target.value = "";
  }
};

$("#bumper-list").addEventListener("change", (e) => {
  const row = e.target.closest(".logo-row");
  if (!row) return;
  const role = e.target.dataset.role;
  if (role) {
    // Satu bumper bisa jadi default pembuka, penutup, keduanya, atau tidak sama sekali.
    brandingCall("/api/branding/default-bumper", {
      method: "POST", body: JSON.stringify({ role, bumper_id: e.target.checked ? row.dataset.id : null }),
    });
    return;
  }
  const field = e.target.dataset.field;
  if (!field) return;
  const value = field === "label" ? e.target.value : field === "keep_audio" ? e.target.checked : Number(e.target.value);
  brandingCall(`/api/branding/bumpers/${row.dataset.id}`, { method: "PATCH", body: JSON.stringify({ [field]: value }) });
});

$("#bumper-list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-bumper=remove]");
  if (!btn) return;
  const row = btn.closest(".logo-row");
  const name = $(".bumper-name", row).value;
  if (!confirm(`Hapus bumper “${name}”? Proyek yang memakainya akan kembali ke default.`)) return;
  brandingCall(`/api/branding/bumpers/${row.dataset.id}`, { method: "DELETE" });
});

$("#btn-add-bumper").onclick = () => $("#bumper-file").click();
$("#bumper-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("label", $("#bumper-label").value.trim());
  $("#brand-msg").textContent = `Mengunggah ${file.name}…`;
  try {
    const data = await api("/api/branding/bumpers", { method: "POST", body: fd });
    renderBranding(data);
    $("#bumper-label").value = "";
    $("#brand-msg").textContent = `Bumper “${data.added.label}” ditambahkan. Centang Pembuka/Penutup untuk memakainya.`;
  } catch (err) {
    $("#brand-msg").textContent = err.message;
  } finally {
    e.target.value = "";
  }
};

function renderAccounts(list) {
  const box = $("#buffer-accounts");
  box.innerHTML = list.length
    ? list.map((a) => `<div class="account-row" data-id="${esc(a.id)}">
        <span>${esc(a.label)}</span><span class="hint">${esc(a.key_hint)}</span>
        <span class="spacer"></span>
        <button type="button" class="ghost small-btn" data-acc="rename">Ganti nama</button>
        <button type="button" class="ghost small-btn danger" data-acc="remove">Hapus</button>
      </div>`).join("")
    : `<p class="muted small">Belum ada akun Buffer.</p>`;
}

$("#buffer-accounts").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-acc]");
  if (!btn) return;
  const row = btn.closest(".account-row");
  const id = row.dataset.id;
  const name = row.firstElementChild.textContent;
  try {
    if (btn.dataset.acc === "remove") {
      if (!confirm(`Hapus akun Buffer “${name}”? Klip yang sudah diposting tidak terpengaruh.`)) return;
      const { accounts } = await api(`/api/buffer/accounts/${id}`, { method: "DELETE" });
      renderAccounts(accounts);
      toast("Akun dihapus.");
    } else {
      const label = prompt("Nama akun:", name);
      if (!label) return;
      const { accounts } = await api(`/api/buffer/accounts/${id}`, { method: "PATCH", body: JSON.stringify({ label }) });
      renderAccounts(accounts);
    }
    state.config = applyStoredAi(await api("/api/config"));
  } catch (err) {
    toast(err.message, true);
  }
});

$("#btn-add-account").onclick = async () => {
  const key = $("#acc-key").value.trim();
  if (!key) return toast("Isi Buffer API key dulu.", true);
  const btn = $("#btn-add-account");
  btn.disabled = true;
  $("#acc-msg").textContent = "Mengecek API key…";
  try {
    const { added, accounts } = await api("/api/buffer/accounts", {
      method: "POST", body: JSON.stringify({ label: $("#acc-label").value.trim(), api_key: key }),
    });
    $("#acc-key").value = "";
    $("#acc-label").value = "";
    renderAccounts(accounts);
    state.config = applyStoredAi(await api("/api/config"));
    $("#acc-msg").textContent = `Akun “${added.label}” ditambahkan (${added.organizations.join(", ")}).`;
  } catch (err) {
    $("#acc-msg").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
};

function switchSettingsTab(tabName) {
  const tabs = document.querySelectorAll(".settings-nav-item[data-set-tab], .settings-tabs button[data-set-tab]");
  tabs.forEach((b) => b.classList.toggle("active", b.dataset.setTab === tabName));
  const panes = document.querySelectorAll("[data-set-pane]");
  panes.forEach((p) => {
    p.hidden = p.dataset.setPane !== tabName;
  });
}

function showSettings(targetTab) {
  state.backTo = state.current ? { view: "job", id: state.current } : { view: $("#view-usage").hidden ? "new" : "usage" };
  state.current = null;
  setView("#view-settings");
  $("#src-video").removeAttribute("src");
  clearDirty();
  if (state.config) fillSettings();
  renderUserSettings();
  switchSettingsTab(typeof targetTab === "string" ? targetTab : "account");
  $("#host-test").textContent = "";
  $("#buffer-test").textContent = "";
  $("#settings-status").textContent = "";
  window.scrollTo(0, 0);
  renderJobList();
  loadBranding();
}

function leaveSettings() {
  const back = state.backTo || { view: "new" };
  if (back.view === "job" && state.jobs[back.id]) openJob(back.id);
  else if (back.view === "usage") showUsage();
  else showNew();
}

document.querySelectorAll(".settings-nav-item[data-set-tab], .settings-tabs button[data-set-tab]").forEach((btn) => {
  btn.onclick = () => switchSettingsTab(btn.dataset.setTab);
});
document.querySelectorAll("[data-close]").forEach((btn) => (btn.onclick = () => $(`#${btn.dataset.close}`).close()));
$("#btn-settings").onclick = () => showSettings();
$("#btn-settings-back").onclick = leaveSettings;
function showHostFields() {
  const selHost = $("#set-host") ? $("#set-host").value : "default";
  document.querySelectorAll("[data-host]").forEach((el) => {
    el.hidden = el.dataset.host !== selHost;
  });
}
$("#set-host").onchange = () => {
  showHostFields();
  fillMediaSettings();
  updateRetentionUI();
};
$("#set-provider").onchange = () => {
  $("#set-key").value = "";
  delete $("#set-model").dataset.dirty;
  fillProviderFields();
};
$("#btn-test-buffer").onclick = async () => {
  const out = $("#buffer-test");
  out.textContent = "Menghubungkan…";
  try {
    const { channels, accounts, errors } = await api("/api/buffer/channels?refresh=true");
    out.textContent = `${accounts.length} akun · ${channels.length} channel`
      + (errors.length ? ` · ${errors.join(" | ")}` : "");
    state.config = applyStoredAi(await api("/api/config"));
    fillSettings();
  } catch (err) {
    out.textContent = err.message;
  }
};
$("#btn-load-models").onclick = async () => {
  const btn = $("#btn-load-models");
  btn.disabled = true;
  try {
    const key = $("#set-key").value.trim();
    const provider = currentProvider();
    const model = $("#set-model").value;
    if (key || model) {
      await api("/api/credentials/ai", {
        method: "POST",
        body: JSON.stringify({ provider, key: key || null, model }),
      });
      await loadAiCredentials();
    }
    const { models } = await api(`/api/models?provider=${provider}`, {
      headers: aiHeaders(provider),
    });
    const sel = $("#set-model");
    const current = sel.value;
    sel.innerHTML = "";
    // Filter model yang tidak tersedia (seperti 2.5 flash dll)
    const availableModels = (models || []).filter((m) => !isModelUnavailable(m));
    availableModels.forEach((m) => sel.add(new Option(m, m)));
    if (availableModels.includes(current) && !isModelUnavailable(current)) {
      sel.value = current;
    } else if (availableModels.length) {
      sel.value = availableModels[0];
      await api("/api/credentials/ai", {
        method: "POST",
        body: JSON.stringify({ provider, key: null, model: availableModels[0] }),
      }).catch(() => {});
      await loadAiCredentials();
    }
    toast(`Terhubung ke ${state.config.providers[provider].label} · ${availableModels.length} model aktif tersedia`);
    $("#set-key").value = "";
    delete $("#set-key").dataset.dirty;
    state.config = applyStoredAi(await api("/api/config"));
    fillSettings();
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
  }
};
async function saveSettings() {
  const provider = currentProvider();
  const key = $("#set-key").value.trim();
  const model = $("#set-model").value;
  const whisper = $("#set-whisper").value;
  const lang = $("#set-lang").value;

  // Simpan preferensi UI non-sensitif ke localStorage
  const userCfg = getUserConfig();
  userCfg.provider = provider;
  userCfg.whisper_model = whisper;
  userCfg.whisper_language = lang;
  saveUserConfig(userCfg);

  // Simpan kredensial AI ke cookie HttpOnly terenkripsi via API
  if (key || model) {
    try {
      await api("/api/credentials/ai", {
        method: "POST",
        body: JSON.stringify({ provider, key: key || null, model }),
      });
    } catch (e) {
      toast("Gagal menyimpan kredensial AI: " + e.message, true);
    }
  }

  // Simpan pengaturan hosting kustom langsung ke cookie HttpOnly terenkripsi
  const selectedHost = $("#set-host") ? $("#set-host").value : "default";
  const creds = {};
  if (selectedHost === "cloudinary" || selectedHost === "r2") {
    document.querySelectorAll(`[data-host="${selectedHost}"] [data-media-field]`).forEach((inp) => {
      if (inp.value.trim()) {
        creds[inp.dataset.mediaField] = inp.value.trim();
      }
    });
  }
  try {
    await api("/api/credentials/media", {
      method: "POST",
      body: JSON.stringify({ host: selectedHost, credentials: creds }),
    });
  } catch (e) {
    toast("Gagal menyimpan kredensial media: " + e.message, true);
  }

  // Bersihkan data lama dari localStorage (zero unencrypted secrets in localStorage)
  localStorage.removeItem(AI_STORAGE_KEY);
  localStorage.removeItem(USER_MEDIA_KEY);
  localStorage.removeItem(USER_TOKEN_KEY);

  await Promise.all([loadAiCredentials(), loadMediaCredentials()]);
  updateRetentionUI();

  // Sinkronkan pengaturan non-kredensial ke server jika bukan public mode
  if (!state.config?.public_mode) {
    try {
      const body = {
        provider, model,
        whisper_model: whisper, whisper_language: lang,
      };
      await api("/api/config", {
        method: "POST",
        body: JSON.stringify(body),
      });
    } catch (e) {
      console.warn("Sinkronisasi server opsional:", e);
    }
  }

  $("#set-key").value = "";
  clearDirty();
  state.config = applyStoredAi(await api("/api/config").catch(() => state.config));
  fillSettings();
}
// Tombol Simpan maupun Enter di kolom isian sama-sama menyimpan.
settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#btn-save-settings");
  btn.disabled = true;
  try {
    await saveSettings();
    const selHost = $("#set-host") ? $("#set-host").value : "default";
    if (selHost !== "default" && !userHasCustomMedia()) {
      $("#settings-status").textContent = "Tersimpan, namun kredensial hosting kustom belum lengkap.";
    } else {
      $("#settings-status").textContent = "Tersimpan.";
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
    const selectedHost = $("#set-host") ? $("#set-host").value : "default";
    let creds = {};
    if (selectedHost === "cloudinary" || selectedHost === "r2") {
      document.querySelectorAll(`[data-host="${selectedHost}"] [data-media-field]`).forEach((inp) => {
        if (inp.value.trim()) {
          creds[inp.dataset.mediaField] = inp.value.trim();
        }
      });
      if (Object.keys(creds).length > 0) {
        await api("/api/credentials/media", {
          method: "POST",
          body: JSON.stringify({ host: selectedHost, credentials: creds }),
        });
        await loadMediaCredentials();
      }
    }
    const r = await api("/api/mediahost/test", {
      method: "POST",
      body: JSON.stringify({ provider: selectedHost, credentials: creds }),
    });
    out.textContent = r.message;
    fillMediaSettings();
    updateRetentionUI();
  } catch (err) {
    out.textContent = err.message;
  }
};

// ---------- Autentikasi & Akun Pengguna ----------

function updateAuthUI() {
  const btnAuthOpen = $("#btn-auth-open");
  const btnUserBadge = $("#btn-user-badge");
  const topbarUsername = $("#topbar-username");

  if (state.user) {
    if (btnAuthOpen) btnAuthOpen.hidden = true;
    if (btnUserBadge) {
      btnUserBadge.hidden = false;
      if (topbarUsername) topbarUsername.textContent = state.user.username;
    }
  } else {
    if (btnAuthOpen) btnAuthOpen.hidden = false;
    if (btnUserBadge) btnUserBadge.hidden = true;
  }
  renderUserSettings();
}

async function checkAuth() {
  try {
    const res = await api("/api/auth/me");
    state.user = res.user || null;
    localStorage.removeItem(USER_TOKEN_KEY);
    updateAuthUI();
  } catch {
    state.user = null;
    localStorage.removeItem(USER_TOKEN_KEY);
    updateAuthUI();
  }
}

function showAuth(mode = "login") {
  state.backTo = state.current
    ? { view: "job", id: state.current }
    : { view: $("#view-settings").hidden ? ($("#view-usage").hidden ? "new" : "usage") : "settings" };
  state.current = null;
  setView("#view-auth");
  setAuthTab(mode);
  $("#src-video").removeAttribute("src");
  const alertEl = $("#auth-alert");
  if (alertEl) {
    alertEl.hidden = true;
    alertEl.textContent = "";
  }
  window.scrollTo(0, 0);
  renderJobList();
}

function setAuthTab(mode) {
  const isLogin = mode === "login";
  $("#tab-login").classList.toggle("active", isLogin);
  $("#tab-register").classList.toggle("active", !isLogin);
  $("#form-login").hidden = !isLogin;
  $("#form-register").hidden = isLogin;
  $("#auth-heading").textContent = isLogin ? "Masuk ke Akun" : "Daftar Akun Baru";
  $("#auth-sub").textContent = isLogin
    ? "Kelola token kredensial dan simpan preferensi studio Anda."
    : "Daftar sekarang untuk mendapatkan token akses otomatis yang terenkripsi aman.";
  const alertEl = $("#auth-alert");
  if (alertEl) {
    alertEl.hidden = true;
    alertEl.textContent = "";
  }
}

function renderUserSettings() {
  const guestBox = $("#settings-user-guest");
  const authBox = $("#settings-user-authenticated");
  const loggedActions = $("#settings-user-logged-actions");
  if (!guestBox || !authBox) return;

  if (state.user) {
    guestBox.hidden = true;
    authBox.hidden = false;
    if (loggedActions) loggedActions.hidden = false;

    $("#user-display-username").textContent = state.user.username;
    $("#user-display-email").textContent = state.user.email;
    if (state.user.created_at) {
      try {
        const d = new Date(state.user.created_at);
        $("#user-display-joined").textContent = d.toLocaleDateString("id-ID", {
          year: "numeric",
          month: "short",
          day: "numeric",
        });
      } catch {
        $("#user-display-joined").textContent = state.user.created_at;
      }
    } else {
      $("#user-display-joined").textContent = "-";
    }

    const tokenInput = $("#user-token-display");
    if (tokenInput) {
      tokenInput.value = state.user.credential_token || "";
    }
    const tokenFeedback = $("#token-feedback");
    if (tokenFeedback) {
      tokenFeedback.textContent = "";
      tokenFeedback.hidden = true;
    }
    const customInput = $("#in-custom-token");
    if (customInput) customInput.value = "";
  } else {
    guestBox.hidden = false;
    authBox.hidden = true;
    if (loggedActions) loggedActions.hidden = true;
  }
}

// Navigasi & interaksi halaman Auth
$("#btn-auth-open").onclick = () => showAuth("login");
$("#btn-user-badge").onclick = () => {
  showSettings();
  const card = $("#settings-user-card");
  if (card) card.scrollIntoView({ behavior: "smooth" });
};
$("#btn-settings-open-auth").onclick = () => showAuth("login");

$("#btn-auth-back").onclick = () => {
  const back = state.backTo || { view: "new" };
  if (back.view === "job" && state.jobs[back.id]) openJob(back.id);
  else if (back.view === "settings") showSettings();
  else if (back.view === "usage") showUsage();
  else showNew();
};

$("#tab-login").onclick = () => setAuthTab("login");
$("#tab-register").onclick = () => setAuthTab("register");
$("#link-switch-to-reg").onclick = () => setAuthTab("register");
$("#link-switch-to-login").onclick = () => setAuthTab("login");

// Toggle lihat password
document.querySelectorAll(".btn-toggle-pwd").forEach((btn) => {
  btn.onclick = () => {
    const target = $(`#${btn.dataset.for}`);
    if (!target) return;
    const isPwd = target.type === "password";
    target.type = isPwd ? "text" : "password";
    btn.innerHTML = isPwd
      ? '<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg>'
      : '<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
    btn.title = isPwd ? "Sembunyikan kata sandi" : "Lihat kata sandi";
  };
});

// Form Login submit
$("#form-login").onsubmit = async (e) => {
  e.preventDefault();
  const btn = $("#btn-login-submit");
  const alertEl = $("#auth-alert");
  alertEl.hidden = true;
  alertEl.className = "alert-box";

  const identifier = $("#login-identifier").value.trim();
  const password = $("#login-password").value;
  if (!identifier || !password) return;

  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Memproses...";
  try {
    const res = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username_or_email: identifier, password }),
    });
    state.user = res.user;
    localStorage.removeItem(USER_TOKEN_KEY);
    updateAuthUI();
    toast(`Berhasil masuk! Selamat datang, ${state.user.username}`);
    $("#login-password").value = "";

    if (state.backTo?.view === "settings") showSettings();
    else if (state.backTo?.view === "job" && state.jobs[state.backTo.id]) openJob(state.backTo.id);
    else showNew();
  } catch (err) {
    alertEl.textContent = err.message;
    alertEl.className = "alert-box error";
    alertEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
};

// Form Register submit
$("#form-register").onsubmit = async (e) => {
  e.preventDefault();
  const btn = $("#btn-reg-submit");
  const alertEl = $("#auth-alert");
  alertEl.hidden = true;
  alertEl.className = "alert-box";

  const username = $("#reg-username").value.trim();
  const email = $("#reg-email").value.trim();
  const password = $("#reg-password").value;
  if (!username || !email || !password) return;

  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Mendaftarkan...";
  try {
    const res = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    });
    state.user = res.user;
    localStorage.removeItem(USER_TOKEN_KEY);
    updateAuthUI();
    toast(`Akun '${state.user.username}' berhasil dibuat! Token kredensial aktif.`);
    $("#reg-password").value = "";
    showSettings();
  } catch (err) {
    alertEl.textContent = err.message;
    alertEl.className = "alert-box error";
    alertEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
};

// Interaksi Token Kredensial di Pengaturan
$("#btn-toggle-token").onclick = () => {
  const input = $("#user-token-display");
  const btn = $("#btn-toggle-token");
  const isPwd = input.type === "password";
  input.type = isPwd ? "text" : "password";
  btn.innerHTML = isPwd
    ? '<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg> Sembunyikan'
    : '<svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg> Lihat';
};

$("#btn-copy-token").onclick = async () => {
  const token = state.user?.credential_token;
  if (!token) return;
  try {
    await navigator.clipboard.writeText(token);
    toast("Token kredensial disalin ke papan klip!");
  } catch {
    const input = $("#user-token-display");
    input.type = "text";
    input.select();
    document.execCommand("copy");
    input.type = "password";
    toast("Token kredensial disalin ke papan klip!");
  }
};

$("#btn-regen-token").onclick = async () => {
  if (!confirm("Buat token acak baru? Token kredensial yang lama tidak akan bisa dipakai lagi.")) return;
  const btn = $("#btn-regen-token");
  btn.disabled = true;
  try {
    const res = await api("/api/auth/token/regenerate", { method: "POST" });
    state.user.credential_token = res.credential_token;
    localStorage.removeItem(USER_TOKEN_KEY);
    $("#user-token-display").value = res.credential_token;
    const fb = $("#token-feedback");
    fb.textContent = "Token baru berhasil dibuat.";
    fb.className = "small ok";
    fb.hidden = false;
    toast("Token baru berhasil dibuat!");
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
  }
};

$("#btn-save-custom-token").onclick = async () => {
  const custom = $("#in-custom-token").value.trim();
  const fb = $("#token-feedback");
  fb.hidden = true;
  if (!custom) {
    fb.textContent = "Masukkan token kustom yang diinginkan (minimal 8 karakter).";
    fb.className = "small err";
    fb.hidden = false;
    return;
  }
  const btn = $("#btn-save-custom-token");
  btn.disabled = true;
  try {
    const res = await api("/api/auth/token", {
      method: "PATCH",
      body: JSON.stringify({ token: custom }),
    });
    state.user.credential_token = res.credential_token;
    localStorage.removeItem(USER_TOKEN_KEY);
    $("#user-token-display").value = res.credential_token;
    $("#in-custom-token").value = "";
    fb.textContent = "Token kustom berhasil disimpan.";
    fb.className = "small ok";
    fb.hidden = false;
    toast("Token kustom berhasil disimpan!");
  } catch (err) {
    fb.textContent = err.message;
    fb.className = "small err";
    fb.hidden = false;
  } finally {
    btn.disabled = false;
  }
};

$("#btn-user-logout").onclick = async () => {
  if (!confirm("Apakah Anda yakin ingin keluar dari akun?")) return;
  try {
    await api("/api/auth/logout", { method: "POST" });
    state.user = null;
    localStorage.removeItem(USER_TOKEN_KEY);
    updateAuthUI();
    toast("Anda telah keluar dari akun.");
  } catch (err) {
    toast(err.message, true);
  }
};

(async () => {
  await migrateLegacyLocalStorage();
  await checkAuth();
  await Promise.all([loadConfig(), loadUsage().catch((err) => toast(err.message, true))]);
  loadBranding();
  connect();
})();
