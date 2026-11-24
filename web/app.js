"use strict";

/* ytconverter web — frontend
 *
 * Flow: paste/share one or more URLs -> each becomes a row, analyzed with
 * /api/info -> user picks global options (+ optional per-row clip) ->
 * "Download" runs the rows ONE AT A TIME: POST /api/jobs, poll the job,
 * then save the file from /api/jobs/:id/file.
 */

const { t } = window.I18n;
const $ = (id) => document.getElementById(id);

const MAX_ITEMS = 20;
const ANALYZE_CONCURRENCY = 2;
const POLL_MS = 800;
const PREFS_KEY = "ytc.prefs";

const el = {
  form: $("pasteForm"), url: $("urlInput"), pasteBtn: $("pasteBtn"), notice: $("notice"),
  workspace: $("workspace"), items: $("items"), rowTpl: $("rowTpl"),
  tabVideo: $("tabVideo"), tabAudio: $("tabAudio"),
  videoOpts: $("videoOpts"), audioOpts: $("audioOpts"),
  quality: $("quality"), videoFormat: $("videoFormat"),
  audioFormat: $("audioFormat"), bitrate: $("bitrate"), bitrateField: $("bitrateField"),
  optSubs: $("optSubs"), optThumb: $("optThumb"),
  runBtn: $("runBtn"), runFill: $("runFill"), runLabel: $("runLabel"),
  clearBtn: $("clearBtn"), hint: $("hint"),
  status: $("status"), statusText: $("statusText"), installBtn: $("installBtn"),
};

/* ---------- state ---------- */
const items = [];             // queue rows (see newItem)
let nextUid = 1;
let health = null;            // last /api/health
let lossless = [];
const run = { active: false, stop: false, total: 0, finished: 0, current: null };

/* ---------- preferences (remembered in this browser) ---------- */
const DEFAULT_PREFS = {
  kind: "video", quality: 1080, videoFormat: "mp4",
  audioFormat: "mp3", bitrate: 192, subs: false, thumb: false,
};
function loadPrefs() {
  try { return { ...DEFAULT_PREFS, ...(JSON.parse(localStorage.getItem(PREFS_KEY)) || {}) }; }
  catch { return { ...DEFAULT_PREFS }; }
}
function savePrefs() {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* storage blocked */ }
}
const prefs = loadPrefs();

/* ---------- api ---------- */
async function api(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    throw { code: "network" };
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw { code: (data.detail && data.detail.code) || "internal_error" };
  return data;
}
const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/* ---------- helpers ---------- */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const errText = (code) => {
  const key = `err.${code}`;
  const s = t(key);
  return s === key ? t("err.unknown") : s;
};

function extractUrls(text) {
  const found = (text || "").match(/https?:\/\/[^\s<>"'`]+/gi) || [];
  // Trailing punctuation from chat messages ("…watch?v=x).") is not part of the URL.
  return [...new Set(found.map((u) => u.replace(/[.,;:!?)\]}>]+$/, "")))];
}

function fmtBytes(n) {
  if (!n) return "";
  const units = lang() === "fr" ? ["o", "Ko", "Mo", "Go"] : ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}
const lang = () => window.I18n.lang;

function fmtClock(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

function showNotice(msg) {
  el.notice.textContent = msg || "";
  el.notice.classList.toggle("hidden", !msg);
}

function option(value, label) {
  const o = document.createElement("option");
  o.value = value; o.textContent = label;
  return o;
}

/* ---------- time parsing for clips ---------- */
/* "90" | "1:30" | "1:02:03" | "1:30.5"  ->  seconds; null when empty; NaN when invalid */
function parseTime(raw) {
  const s = (raw || "").trim().replace(",", ".");
  if (!s) return null;
  if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d+)?$/.test(s)) return NaN;
  const parts = s.split(":").map(Number);
  if (parts.slice(1).some((p) => p >= 60)) return NaN;
  return parts.reduce((acc, p) => acc * 60 + p, 0);
}

function validateClip(item) {
  const start = parseTime(item.clipStart);
  const end = parseTime(item.clipEnd);
  let err = "";
  if (Number.isNaN(start) || Number.isNaN(end)) err = "clip.err_format";
  else if (start != null && end != null && end <= start) err = "clip.err_order";
  else if (start != null && item.info && item.info.duration_seconds && start >= item.info.duration_seconds) err = "clip.err_range";
  item.clipError = err;
  renderClipError(item);
  return !err;
}

function clipRange(item) {
  const s = parseTime(item.clipStart), e = parseTime(item.clipEnd);
  if ((s == null || Number.isNaN(s) || s === 0) && (e == null || Number.isNaN(e))) return "";
  const from = s && !Number.isNaN(s) ? fmtClock(s) : "0:00";
  const to = e != null && !Number.isNaN(e) ? fmtClock(e) : "…";
  return `${from}–${to}`;
}

/* ---------- options ---------- */
function readOptions() {
  return {
    kind: el.tabVideo.getAttribute("aria-pressed") === "true" ? "video" : "audio",
    quality: Number(el.quality.value),
    videoFormat: el.videoFormat.value,
    audioFormat: el.audioFormat.value,
    bitrate: Number(el.bitrate.value) || prefs.bitrate,   // select is empty until /api/health answers
    subs: el.optSubs.checked,
    thumb: el.optThumb.checked,
  };
}

function fillQuality() {
  const heights = (health ? health.options.qualities : [144, 240, 360, 480, 720, 1080, 1440, 2160]).slice().reverse();
  const current = el.quality.value !== "" ? Number(el.quality.value) : prefs.quality;
  el.quality.replaceChildren(
    option(0, t("opt.quality_max")),
    ...heights.map((h) => option(h, h === 2160 ? "2160p (4K)" : `${h}p`)),
  );
  el.quality.value = String(heights.includes(current) || current === 0 ? current : 1080);
}

function fillStaticOptions(o) {
  lossless = o.lossless_audio;
  el.videoFormat.replaceChildren(...o.video_formats.map((f) => option(f, f.toUpperCase())));
  el.audioFormat.replaceChildren(...o.audio_formats.map((f) => option(f, f.toUpperCase())));
  el.bitrate.replaceChildren(...o.audio_bitrates.map((b) => option(b, `${b} kb/s`)));
  fillQuality();
}

function applyPrefsToControls() {
  setKind(prefs.kind, false);
  if ([...el.videoFormat.options].some((o) => o.value === prefs.videoFormat)) el.videoFormat.value = prefs.videoFormat;
  if ([...el.audioFormat.options].some((o) => o.value === prefs.audioFormat)) el.audioFormat.value = prefs.audioFormat;
  if ([...el.bitrate.options].some((o) => o.value === String(prefs.bitrate))) el.bitrate.value = String(prefs.bitrate);
  el.optSubs.checked = !!prefs.subs;
  el.optThumb.checked = !!prefs.thumb;
  syncBitrateVisibility();
}

function setKind(kind, persist = true) {
  const video = kind === "video";
  el.tabVideo.setAttribute("aria-pressed", video);
  el.tabAudio.setAttribute("aria-pressed", !video);
  el.tabVideo.classList.toggle("active", video);
  el.tabAudio.classList.toggle("active", !video);
  el.videoOpts.classList.toggle("hidden", !video);
  el.audioOpts.classList.toggle("hidden", video);
  if (persist) onOptionsChanged();
}

function syncBitrateVisibility() {
  el.bitrateField.classList.toggle("hidden", lossless.includes(el.audioFormat.value));
}

function onOptionsChanged() {
  Object.assign(prefs, readOptions());
  savePrefs();
  syncBitrateVisibility();
  items.forEach(updateRow);   // "ready" rows show the planned output
  updateRunButton();
}

function subLangs() {
  return lang() === "fr" ? ["fr", "en"] : ["en"];
}

/* What a row will produce with the current options, e.g. "MP4 · 1080p". */
function plannedSummary(item) {
  const o = readOptions();
  const parts = [];
  if (o.kind === "video") parts.push(`${o.videoFormat.toUpperCase()} · ${o.quality ? o.quality + "p" : t("opt.quality_max").toLowerCase()}`);
  else parts.push(o.audioFormat.toUpperCase() + (lossless.includes(o.audioFormat) ? "" : ` · ${o.bitrate} kb/s`));
  const range = clipRange(item);
  if (range) parts.push(t("item.clip_summary", { range }));
  return parts.join(" · ");
}

/* ---------- server status ---------- */
function renderStatus() {
  if (!health) {
    el.status.className = "status down";
    el.statusText.textContent = t("status.down");
  } else {
    el.status.className = "status " + (health.ffmpeg ? "ok" : "warn");
    el.statusText.textContent = t(health.ffmpeg ? "status.ok" : "status.noffmpeg", { v: health.yt_dlp });
  }
  el.status.title = el.statusText.textContent;
}

async function loadHealth() {
  try {
    health = await api("/api/health");
    fillStaticOptions(health.options);
    applyPrefsToControls();
  } catch {
    health = null;
  }
  renderStatus();
  items.forEach(updateRow);
  updateRunButton();
}

/* ---------- rows ---------- */
function newItem(url) {
  return {
    uid: nextUid++, url, status: "analyzing", info: null, error: "",
    jobId: null, progress: 0, speed: null, eta: null,
    filename: "", filesize: 0, expires: 0,
    clipOpen: false, clipStart: "", clipEnd: "", clipError: "",
    removed: false, row: null,
  };
}

function mountRow(item) {
  const row = el.rowTpl.content.firstElementChild.cloneNode(true);
  window.I18n.apply(row);
  const q = (sel) => row.querySelector(sel);

  item.row = {
    li: row,
    img: q(".thumb img"), dur: q(".thumb-dur"),
    title: q(".item-title"), sub: q(".item-sub"), status: q(".item-status"),
    bar: q(".item-bar i"), clip: q(".clip"),
    clipBtn: q(".clip-btn"), saveBtn: q(".save-btn"), retryBtn: q(".retry-btn"), rmBtn: q(".rm-btn"),
    clipStart: q(".clip-start"), clipEnd: q(".clip-end"), clipErr: q(".clip-err"),
  };
  const r = item.row;

  r.rmBtn.addEventListener("click", () => removeItem(item));
  r.saveBtn.addEventListener("click", () => item.jobId && saveFile(item.jobId));
  r.retryBtn.addEventListener("click", () => retryItem(item));
  r.clipBtn.addEventListener("click", () => {
    item.clipOpen = !item.clipOpen;
    updateRow(item);
    if (item.clipOpen) r.clipStart.focus();
  });
  const onClipInput = () => {
    item.clipStart = r.clipStart.value;
    item.clipEnd = r.clipEnd.value;
    validateClip(item);
    updateRow(item);
  };
  r.clipStart.addEventListener("input", onClipInput);
  r.clipEnd.addEventListener("input", onClipInput);

  el.items.appendChild(row);
  updateRow(item);
}

function renderClipError(item) {
  if (item.row) item.row.clipErr.textContent = item.clipError ? t(item.clipError) : "";
}

function updateRow(item) {
  const r = item.row;
  if (!r) return;
  const info = item.info;
  const st = item.status;

  r.li.className = `item st-${st}`;
  r.title.textContent = info ? info.title : hostOf(item.url);
  r.title.title = info ? info.title : item.url;
  r.sub.textContent = info ? [info.uploader, info.site].filter(Boolean).join(" · ") : item.url;

  if (info && info.thumbnail) {
    if (r.img.getAttribute("src") !== info.thumbnail) r.img.src = info.thumbnail;
  } else {
    r.img.removeAttribute("src");
  }
  r.dur.textContent = info ? info.duration : "";

  // status line
  let text = "";
  switch (st) {
    case "analyzing": text = t("item.analyzing"); break;
    case "ready": text = plannedSummary(item); break;
    case "queued": text = t("item.queued"); break;
    case "downloading": {
      const bits = [];
      bits.push(item.progress > 0 ? `${t("item.downloading")} · ${Math.floor(item.progress)} %` : t("item.downloading") + "…");
      if (item.speed) bits.push(`${fmtBytes(item.speed)}/s`);
      if (item.eta != null) bits.push(t("item.eta", { eta: fmtClock(item.eta) }));
      text = bits.join(" · ");
      break;
    }
    case "processing": text = t("item.processing"); break;
    case "done": text = t("item.done", { size: fmtBytes(item.filesize), min: Math.max(1, Math.ceil(item.expires / 60)) }); break;
    case "failed": case "invalid": text = errText(item.error); break;
  }
  r.status.textContent = text;
  r.status.title = item.filename || "";

  // progress bar
  const pct = st === "done" ? 100 : st === "processing" ? 99 : st === "downloading" ? item.progress : 0;
  r.bar.style.transform = `scaleX(${pct / 100})`;

  // buttons
  const idle = st === "ready" || st === "failed";
  r.clipBtn.classList.toggle("hidden", !(idle && info));
  r.clipBtn.classList.toggle("on", !!clipRange(item));
  r.clipBtn.setAttribute("aria-expanded", item.clipOpen);
  r.saveBtn.classList.toggle("hidden", st !== "done");
  r.retryBtn.classList.toggle("hidden", !(st === "failed" || st === "invalid" || st === "done"));
  const retryLabel = t(st === "done" ? "item.redo" : "item.retry");   // done: same link, other options
  r.retryBtn.title = retryLabel;
  r.retryBtn.setAttribute("aria-label", retryLabel);
  r.clip.classList.toggle("hidden", !(item.clipOpen && idle && info));
  renderClipError(item);
}

function setStatus(item, status) {
  item.status = status;
  updateRow(item);
  updateRunButton();
}

/* ---------- adding links ---------- */
function addUrls(urls) {
  showNotice("");
  const fresh = urls.filter((u) => !items.some((i) => i.url === u));
  if (!urls.length) { showNotice(t("err.no_url")); return; }
  if (!fresh.length) return;

  const room = MAX_ITEMS - items.length;
  if (fresh.length > room) showNotice(t("err.too_many_items", { max: MAX_ITEMS }));

  for (const url of fresh.slice(0, Math.max(room, 0))) {
    const item = newItem(url);
    items.push(item);
    mountRow(item);
    enqueueAnalyze(item);
  }
  refreshWorkspace();
}

const analyzeQueue = [];
let analyzing = 0;
function enqueueAnalyze(item) {
  analyzeQueue.push(item);
  pumpAnalyze();
}
function pumpAnalyze() {
  while (analyzing < ANALYZE_CONCURRENCY && analyzeQueue.length) {
    const item = analyzeQueue.shift();
    if (item.removed) continue;
    analyzing++;
    analyzeItem(item).finally(() => { analyzing--; pumpAnalyze(); });
  }
}
async function analyzeItem(item) {
  try {
    const info = await post("/api/info", { url: item.url });
    if (item.removed) return;
    item.info = info;
    item.error = "";
    setStatus(item, "ready");
  } catch (e) {
    if (item.removed) return;
    item.error = e.code;
    setStatus(item, "invalid");
  }
}

function retryItem(item) {
  if (run.active && item.status === "done") return;   // wait for the current run to end
  item.error = "";
  if (item.info) {
    setStatus(item, "ready");
  } else {
    setStatus(item, "analyzing");
    enqueueAnalyze(item);
  }
}

function removeItem(item) {
  item.removed = true;
  cancelJob(item);
  const i = items.indexOf(item);
  if (i >= 0) items.splice(i, 1);
  item.row.li.remove();
  refreshWorkspace();
}

function clearAll() {
  [...items].forEach(removeItem);
  showNotice("");
}

function refreshWorkspace() {
  el.workspace.classList.toggle("hidden", items.length === 0);
  updateRunButton();
}

/* ---------- running the queue ---------- */
function buildRequest(item, o) {
  const req = { url: item.url, kind: o.kind, subtitles: o.subs, thumbnail: o.thumb };
  if (o.subs) req.sub_langs = subLangs();
  if (o.kind === "video") { req.quality = o.quality; req.format = o.videoFormat; }
  else { req.format = o.audioFormat; req.bitrate = o.bitrate; }

  const start = parseTime(item.clipStart), end = parseTime(item.clipEnd);
  if (start) req.clip_start = start;            // 0 / empty = from the beginning
  if (end != null && !Number.isNaN(end)) req.clip_end = end;
  return req;
}

async function runAll() {
  if (run.active) return;
  const targets = items.filter((i) => i.status === "ready" || i.status === "failed");
  if (!targets.length) return;

  let ok = true;
  for (const item of targets) if (!validateClip(item)) { ok = false; item.clipOpen = true; updateRow(item); }
  if (!ok) { showNotice(t("clip.fix")); return; }
  showNotice("");

  const options = readOptions();           // snapshot: later changes only affect later runs
  Object.assign(run, { active: true, stop: false, total: targets.length, finished: 0, current: null });
  targets.forEach((i) => { i.error = ""; i.progress = 0; setStatus(i, "queued"); });

  for (const item of targets) {
    if (run.stop) break;
    if (item.removed) { run.finished++; continue; }
    run.current = item;
    await processItem(item, options);
    run.finished++;
    updateRunButton();
  }

  items.forEach((i) => { if (i.status === "queued") setStatus(i, "ready"); });
  Object.assign(run, { active: false, current: null });
  updateRunButton();
}

async function processItem(item, options) {
  item.progress = 0; item.speed = null; item.eta = null;
  setStatus(item, "downloading");
  try {
    const job = await post("/api/jobs", buildRequest(item, options));
    item.jobId = job.id;

    for (;;) {
      await sleep(POLL_MS);
      if (item.removed || run.stop) {
        cancelJob(item);
        if (!item.removed) setStatus(item, "ready");
        return;
      }
      const j = await api(`/api/jobs/${item.jobId}`);
      if (item.removed) return;
      applyJob(item, j);
      if (j.state === "done") { saveFile(item.jobId); return; }
      if (j.state === "error") return;
    }
  } catch (e) {
    if (item.removed) return;
    item.error = e.code;
    setStatus(item, "failed");
    if (e.code === "rate_limited") run.stop = true;   // hammering won't help
  }
}

function applyJob(item, j) {
  item.progress = j.progress || 0;
  item.speed = j.speed;
  item.eta = j.eta;
  if (j.state === "queued") item.status = "downloading";
  else if (j.state === "downloading") item.status = "downloading";
  else if (j.state === "processing") item.status = "processing";
  else if (j.state === "done") {
    item.status = "done";
    item.filename = j.filename; item.filesize = j.filesize; item.expires = j.expires_in || 0;
  } else if (j.state === "error") {
    item.status = "failed"; item.error = j.error || "internal_error";
  }
  updateRow(item);
  updateRunButton();
}

function cancelJob(item) {
  if (item.jobId && ["downloading", "processing", "queued"].includes(item.status)) {
    fetch(`/api/jobs/${item.jobId}`, { method: "DELETE" }).catch(() => {});
  }
}

function saveFile(id) {
  const a = document.createElement("a");
  a.href = `/api/jobs/${id}/file`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* ---------- main button ---------- */
function updateRunButton() {
  const b = el.runBtn;
  b.className = "dl";
  b.disabled = false;
  el.runFill.style.transform = "scaleX(0)";
  el.hint.textContent = "";
  el.clearBtn.textContent = t(run.active ? "run.stop" : "run.clear");

  if (run.active) {
    const cur = run.current;
    const part = cur ? (cur.status === "done" ? 1 : cur.status === "processing" ? 0.99 : cur.progress / 100) : 0;
    b.classList.add("busy");
    b.disabled = true;
    el.runFill.style.transform = `scaleX(${Math.min((run.finished + part) / Math.max(run.total, 1), 1)})`;
    el.runLabel.textContent = t("run.running", { i: Math.min(run.finished + 1, run.total), n: run.total });
    return;
  }

  const ready = items.filter((i) => i.status === "ready" || i.status === "failed").length;
  const waiting = items.some((i) => i.status === "analyzing");
  const anyDone = items.some((i) => i.status === "done");

  if (ready > 0) {
    el.runLabel.textContent = ready > 1 ? t("run.many", { n: ready }) : t("run.one");
    if (ready > 1) el.hint.textContent = t("run.multi_hint");
  } else if (waiting) {
    b.disabled = true;
    el.runLabel.textContent = t("run.analyzing");
  } else if (anyDone) {
    b.classList.add("done");
    b.disabled = true;
    el.runLabel.textContent = t("run.done");
  } else {
    b.disabled = true;
    el.runLabel.textContent = t("run.one");
  }
}

/* ---------- events ---------- */
el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = el.url.value.trim();
  if (!text) return;
  let urls = extractUrls(text);
  // Be forgiving with a bare "youtube.com/watch?v=…" typed by hand.
  if (!urls.length && /^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(text)) urls = [`https://${text}`];
  if (!urls.length) { showNotice(t("err.no_url")); return; }   // keep the text so it can be fixed
  addUrls(urls);
  el.url.value = "";
});

el.url.addEventListener("paste", (e) => {
  const text = (e.clipboardData || window.clipboardData).getData("text");
  const urls = extractUrls(text);
  if (!urls.length) return;       // not a link: let the browser paste normally
  e.preventDefault();
  addUrls(urls);
  el.url.value = "";
});

el.pasteBtn.addEventListener("click", async () => {
  try {
    addUrls(extractUrls(await navigator.clipboard.readText()));
  } catch {
    el.url.focus();               // clipboard blocked: the user can paste by hand
  }
});

el.tabVideo.addEventListener("click", () => setKind("video"));
el.tabAudio.addEventListener("click", () => setKind("audio"));
[el.quality, el.videoFormat, el.audioFormat, el.bitrate, el.optSubs, el.optThumb]
  .forEach((c) => c.addEventListener("change", onOptionsChanged));

el.runBtn.addEventListener("click", runAll);
el.clearBtn.addEventListener("click", () => { if (run.active) { run.stop = true; } else { clearAll(); } });

document.querySelectorAll("[data-lang]").forEach((b) =>
  b.addEventListener("click", () => {
    window.I18n.setLang(b.dataset.lang);
    fillQuality();
    renderStatus();
    items.forEach((i) => { window.I18n.apply(i.row.li); updateRow(i); });
    updateRunButton();
  }));

/* ---------- PWA: install button + service worker + share target ---------- */
let installPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installPrompt = e;
  el.installBtn.classList.remove("hidden");
});
el.installBtn.addEventListener("click", async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice.catch(() => {});
  installPrompt = null;
  el.installBtn.classList.add("hidden");
});
window.addEventListener("appinstalled", () => el.installBtn.classList.add("hidden"));

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

/* "Share to ytconverter" from another app lands here as ?url=…&text=…&title=… */
function consumeSharedLinks() {
  const q = new URLSearchParams(location.search);
  const shared = ["url", "text", "title"].flatMap((k) => extractUrls(q.get(k) || ""));
  if (q.has("url") || q.has("text") || q.has("title")) history.replaceState(null, "", location.pathname);
  if (shared.length) addUrls([...new Set(shared)]);
}

/* ---------- boot ---------- */
window.I18n.apply();
setKind(prefs.kind, false);
fillQuality();
el.quality.value = String(prefs.quality);
loadHealth().then(consumeSharedLinks);
if (!new URLSearchParams(location.search).toString()) el.url.focus();
