function $(id) { return document.getElementById(id); }
function safeArray(x) { return Array.isArray(x) ? x : []; }
function safeText(x) { return typeof x === "string" ? x : ""; }

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} @ ${url}`);
  return await res.json();
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json())?.detail || ""; } catch (_) {}
    throw new Error(`${res.status} ${res.statusText}${detail ? " - " + detail : ""}`);
  }
  return await res.json();
}

/* Toast */
function showToast(message, type = "info", ms = 2500) {
  const host = $("toastHost");
  if (!host) {
    console.log(`[${type}] ${message}`);
    return null;
  }

  const el = document.createElement("div");
  el.className =
    "glass-card px-4 py-3 text-sm font-semibold max-w-[360px] " +
    "border border-black/10 bg-white/80 backdrop-blur " +
    "shadow-lg transition opacity-0 -translate-y-1 cursor-pointer";

  const prefix =
    type === "success" ? "✅ " :
    type === "error" ? "❌ " :
    type === "loading" ? "⏳ " :
    "ℹ️ ";

  el.textContent = `${prefix}${message}`;
  host.appendChild(el);

  requestAnimationFrame(() => {
    el.classList.remove("opacity-0", "-translate-y-1");
    el.classList.add("opacity-100", "translate-y-0");
  });

  const timer = setTimeout(() => {
    el.classList.add("opacity-0");
    setTimeout(() => el.remove(), 220);
  }, ms);

  el.addEventListener("click", () => {
    clearTimeout(timer);
    el.remove();
  });

  return el;
}

/* =========================
   Google Today
   ========================= */

const GOOGLE_TODAY = { lastDate: "", lastLoadMs: 0, loading: false };

function _formatTimeMaybe(isoOrDateStr) {
  const s = safeText(isoOrDateStr);
  if (!s) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return "All day";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function renderGoogleToday(data) {
  const meta = $("googleTodayMeta");
  const eventsWrap = $("googleEventsList");
  const tasksWrap = $("googleTasksList");
  const eventsEmpty = $("googleEventsEmpty");
  const tasksEmpty = $("googleTasksEmpty");

  if (!eventsWrap || !tasksWrap) return;

  const dateStr = safeText(data?.report_date) || "";
  const exported = safeText(data?.export_timestamp) || "";

  if (meta) {
    meta.textContent = dateStr
      ? `Showing ${dateStr} · last sync ${exported ? exported.replace("T"," ").slice(0,19) : "—"}`
      : `Showing today · last sync ${exported ? exported.replace("T"," ").slice(0,19) : "—"}`;
  }

  const events = safeArray(data?.calendar?.items);
  eventsWrap.innerHTML = "";
  if (!events.length) {
    if (eventsEmpty) eventsEmpty.classList.remove("hidden");
  } else {
    if (eventsEmpty) eventsEmpty.classList.add("hidden");
    for (const e of events) {
      const title = safeText(e?.title) || "(Untitled)";
      const start = _formatTimeMaybe(e?.start);
      const loc = safeText(e?.location) || "N/A";

      const row = document.createElement("div");
      row.className = "p-3 rounded-xl bg-white/60 border border-black/10";
      row.innerHTML = `
        <div class="flex items-start justify-between gap-2">
          <div class="text-sm font-black">${escapeHtml(title)}</div>
          <div class="text-[10px] font-mono opacity-60 shrink-0">${escapeHtml(start)}</div>
        </div>
        <div class="text-xs opacity-70 mt-1">${escapeHtml(loc)}</div>
      `;
      eventsWrap.appendChild(row);
    }
  }

  const tasks = safeArray(data?.tasks?.items);
  tasksWrap.innerHTML = "";
  if (!tasks.length) {
    if (tasksEmpty) tasksEmpty.classList.remove("hidden");
  } else {
    if (tasksEmpty) tasksEmpty.classList.add("hidden");
    for (const t of tasks) {
      const title = safeText(t?.title) || "(Untitled)";
      const listSource = safeText(t?.list_source) || "";
      const status = safeText(t?.status) || "";
      const notes = safeText(t?.notes) || "";

      const row = document.createElement("div");
      row.className = "p-3 rounded-xl bg-white/60 border border-black/10";
      row.innerHTML = `
        <div class="flex items-start justify-between gap-2">
          <div class="text-sm font-black">${escapeHtml(title)}</div>
          <div class="text-[10px] font-mono opacity-60 shrink-0">${escapeHtml(status)}</div>
        </div>
        <div class="text-xs opacity-70 mt-1">${escapeHtml(listSource ? `List: ${listSource}` : "")}</div>
        ${notes ? `<div class="text-xs opacity-60 mt-1">${escapeHtml(notes)}</div>` : ""}
      `;
      tasksWrap.appendChild(row);
    }
  }
}

async function loadGoogleToday(force = false) {
  const dateStr = $("dateInput")?.value || "";
  const now = Date.now();

  if (!force) {
    if (GOOGLE_TODAY.loading) return;
    if (GOOGLE_TODAY.lastDate === dateStr && now - GOOGLE_TODAY.lastLoadMs < 5000) return;
  }

  GOOGLE_TODAY.loading = true;
  try {
    const data = await fetchJson(`/api/google/today?date=${encodeURIComponent(dateStr || "")}`);
    GOOGLE_TODAY.lastDate = dateStr;
    GOOGLE_TODAY.lastLoadMs = Date.now();
    renderGoogleToday(data);
  } finally {
    GOOGLE_TODAY.loading = false;
  }
}

/* =========================
   Privacy state
   ========================= */

const PRIVACY = { apps: [], keywords: [], meta: { privacy_config_file: "" } };

function dedupeCaseInsensitive(arr) {
  const out = [];
  const seen = new Set();
  for (const raw of safeArray(arr)) {
    const s = safeText(raw).trim();
    if (!s) continue;
    const key = s.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

function setTextareasFromState() {
  if ($("blockedAppsInput")) $("blockedAppsInput").value = PRIVACY.apps.join("\n");
  if ($("blockedKeywordsInput")) $("blockedKeywordsInput").value = PRIVACY.keywords.join("\n");
}

function readStateFromTextareas() {
  const apps = ($("blockedAppsInput")?.value || "").split("\n").map(s => s.trim());
  const kws = ($("blockedKeywordsInput")?.value || "").split("\n").map(s => s.trim());
  PRIVACY.apps = dedupeCaseInsensitive(apps);
  PRIVACY.keywords = dedupeCaseInsensitive(kws);
}

function renderTagList(containerId, emptyId, items) {
  const wrap = $(containerId);
  const empty = $(emptyId);
  if (!wrap) return;

  wrap.innerHTML = "";
  const arr = safeArray(items);

  if (!arr.length) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");

  for (const it of arr) {
    const s = safeText(it).trim();
    if (!s) continue;

    const chip = document.createElement("span");
    chip.className =
      "px-3 py-1 rounded-full text-[11px] font-black " +
      "bg-white/70 border border-black/10 shadow-sm";
    chip.textContent = s;

    wrap.appendChild(chip);
  }
}

function renderPrivacyUI() {
  renderTagList("blockedAppsList", "blockedAppsEmpty", PRIVACY.apps);
  renderTagList("blockedKeywordsList", "blockedKeywordsEmpty", PRIVACY.keywords);
  setTextareasFromState();

  if ($("privacyMeta")) {
    $("privacyMeta").textContent = `privacy_config_file: ${PRIVACY.meta.privacy_config_file || "—"}`;
  }
}

function addOne(kind, value) {
  const v = safeText(value).trim();
  if (!v) return { ok: false, reason: "empty" };

  if (kind === "app") {
    const existed = PRIVACY.apps.some(x => x.toLowerCase() === v.toLowerCase());
    if (existed) return { ok: false, reason: "exists" };
    PRIVACY.apps.push(v);
    PRIVACY.apps = dedupeCaseInsensitive(PRIVACY.apps);
    renderPrivacyUI();
    return { ok: true };
  }

  if (kind === "keyword") {
    const existed = PRIVACY.keywords.some(x => x.toLowerCase() === v.toLowerCase());
    if (existed) return { ok: false, reason: "exists" };
    PRIVACY.keywords.push(v);
    PRIVACY.keywords = dedupeCaseInsensitive(PRIVACY.keywords);
    renderPrivacyUI();
    return { ok: true };
  }

  return { ok: false, reason: "bad_kind" };
}

async function loadPrivacyConfig() {
  const out = await fetchJson("/api/privacy/config");
  PRIVACY.apps = dedupeCaseInsensitive(out?.blocked_apps);
  PRIVACY.keywords = dedupeCaseInsensitive(out?.blocked_keywords);
  PRIVACY.meta.privacy_config_file = out?.privacy_config_file || "";
  renderPrivacyUI();
  return out;
}

async function savePrivacyConfig() {
  readStateFromTextareas();
  renderPrivacyUI();

  const out = await postJson("/api/privacy/config", {
    blocked_apps: PRIVACY.apps,
    blocked_keywords: PRIVACY.keywords,
  });

  await loadPrivacyConfig();
  return out;
}

/* =========================
   Original report UI
   ========================= */

function setThemeFromStylePreset(stylePreset) {
  const root = document.documentElement;
  if (!stylePreset) return;
  if (stylePreset.includes("cyber")) root.setAttribute("data-theme", "cyber");
  else if (stylePreset.includes("cute")) root.setAttribute("data-theme", "cute");
  else root.setAttribute("data-theme", "minimal");
}

function setTitle(dateLocal) {
  const t = $("title");
  if (t) t.textContent = dateLocal ? `Daily Recap · ${dateLocal}` : "Daily Recap";
}

function setPills(dateLocal, timezone, stylePreset) {
  const row = $("pillRow");
  if (!row) return;
  row.innerHTML = "";

  const pills = [
    ["Date", dateLocal || "—"],
    ["TZ", timezone || "—"],
    ["Style", stylePreset || "—"],
  ];

  for (const [k, v] of pills) {
    const el = document.createElement("div");
    el.className = "px-3 py-1 rounded-full text-xs font-bold bg-black/5 border border-black/10";
    el.innerHTML = `<span class="opacity-60 mr-1">${escapeHtml(k)}:</span>${escapeHtml(v)}`;
    row.appendChild(el);
  }
}

function renderReadableTimeline(lines) {
  const wrap = $("tab-human");
  if (!wrap) return;
  wrap.innerHTML = "";

  const arr = safeArray(lines);
  if (!arr.length) {
    wrap.innerHTML = `<div class="text-sm opacity-60">No timeline data.</div>`;
    return;
  }

  for (const line of arr) {
    const text = safeText(line);
    const m = text.match(/^(\d{2}:\d{2}–\d{2}:\d{2})\s+(.*)$/);
    const time = m ? m[1] : "";
    const rest = m ? m[2] : text;

    const row = document.createElement("div");
    row.className = "flex gap-3 items-start p-3 rounded-xl bg-black/5 border border-black/10";
    row.innerHTML = `
      <div class="text-xs font-mono opacity-60 w-[92px] shrink-0">${escapeHtml(time)}</div>
      <div class="text-sm font-semibold">${escapeHtml(rest)}</div>
    `;
    wrap.appendChild(row);
  }
}

function renderSegments(segs) {
  const wrap = $("tab-segments");
  if (!wrap) return;
  wrap.innerHTML = "";

  const arr = safeArray(segs);
  if (!arr.length) {
    wrap.innerHTML = `<div class="text-sm opacity-60">No segments.</div>`;
    return;
  }

  for (const seg of arr) {
    const el = document.createElement("div");
    el.className = "p-4 rounded-2xl bg-black/5 border border-black/10";

    const supports = safeArray(seg.supporting_surfaces)
      .map((s) => `<span class="px-2 py-1 rounded-full text-[10px] bg-white/60 border border-black/10">support: ${escapeHtml(s)}</span>`)
      .join("");

    const flags = safeArray(seg.risk_flags)
      .filter((f) => f && f !== "none")
      .map((f) => `<span class="px-2 py-1 rounded-full text-[10px] bg-white/60 border border-black/10">flag: ${escapeHtml(f)}</span>`)
      .join("");

    el.innerHTML = `
      <div class="flex justify-between items-start gap-3">
        <div>
          <div class="text-sm font-black">
            ${escapeHtml(seg.start_time_local)}–${escapeHtml(seg.end_time_local)}
            · ${escapeHtml(seg.dominant_surface || "Unknown")}
          </div>
          <div class="text-xs opacity-70 mt-1">
            ${escapeHtml(seg.activity || "Other")} · ${escapeHtml(String(seg.duration_minutes ?? "—"))} min · conf ${escapeHtml(String(seg.confidence ?? "—"))}
          </div>
        </div>
        <div class="text-[10px] font-mono opacity-60">${escapeHtml(seg.segment_id || "")}</div>
      </div>
      ${seg.context_detail ? `<div class="text-xs opacity-80 mt-3"><b>Context:</b> ${escapeHtml(seg.context_detail)}</div>` : ""}
      ${seg.notes ? `<div class="text-xs opacity-70 mt-2"><b>Notes:</b> ${escapeHtml(seg.notes)}</div>` : ""}
      <div class="flex flex-wrap gap-2 mt-3">
        ${supports}
        ${flags}
      </div>
    `;
    wrap.appendChild(el);
  }
}

function renderFeedback(feedbackObj) {
  const wrap = $("tab-feedback");
  if (!wrap) return;
  wrap.innerHTML = "";

  const events = safeArray(feedbackObj?.events || feedbackObj?.feedback_events || feedbackObj);
  if (!events.length) {
    wrap.innerHTML = `<div class="text-sm opacity-60">No feedback events.</div>`;
    return;
  }

  for (const e of events) {
    const el = document.createElement("div");
    el.className = "p-4 rounded-2xl bg-black/5 border border-black/10";
    const t = e?.ts || e?.time || "";
    const kind = e?.type || e?.event_type || "event";
    const msg = e?.message || e?.text || "";
    el.innerHTML = `
      <div class="text-xs font-mono opacity-60">${escapeHtml(String(t))}</div>
      <div class="text-sm font-black mt-1">${escapeHtml(String(kind))}</div>
      <div class="text-sm opacity-80 mt-2">${escapeHtml(String(msg))}</div>
    `;
    wrap.appendChild(el);
  }
}

function renderVibe(vibe) {
  if (!vibe) return;

  const map = {
    hurried_anxious: "Hurried / Anxious",
    calm_relaxed: "Calm / Relaxed",
    creative_flow: "Creative Flow",
    deep_focus: "Deep Focus",
    distracted_scattered: "Distracted",
    social_connected: "Social / Connected",
    learning_mode: "Learning Mode",
    mixed_unclear: "Mixed / Unclear",
  };

  if ($("vibeBadge")) $("vibeBadge").textContent = map[vibe.primary_vibe] || vibe.primary_vibe || "—";
  if ($("vibeConf")) $("vibeConf").textContent = `confidence ${vibe.confidence ?? "—"}`;

  if ($("vibeWhy")) $("vibeWhy").innerHTML = safeArray(vibe.why).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>—</li>";
  if ($("vibePatterns")) $("vibePatterns").innerHTML = safeArray(vibe.notable_patterns).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>—</li>";

  if ($("caringMessage")) $("caringMessage").textContent = safeText(vibe.caring_message) || "—";
  if ($("quote")) $("quote").textContent = safeText(vibe.quote) || "—";
  if ($("humorAlt")) $("humorAlt").textContent = safeText(vibe.humor_alt) || "—";

  if ($("vibeMeta")) $("vibeMeta").textContent = vibe.primary_vibe ? `primary_vibe: ${vibe.primary_vibe}` : "";
}

function normalizeImageUrl(file) {
  if (!file) return "";
  const s = String(file).replaceAll("\\", "/").trim();
  if (s.includes("artified_backend/screenshots/")) return "/" + s.replace(/^\/?artified_backend\/screenshots\//, "screenshots/");
  if (s.startsWith("/screenshots/")) return s;
  if (s.startsWith("screenshots/")) return "/" + s;
  if (s.startsWith("http://") || s.startsWith("https://")) return s;
  return s;
}

function renderImage(image) {
  const img = $("redrawImg");
  const fallback = $("imageFallback");

  const url =
    image?.redraw_url ||
    image?.url ||
    normalizeImageUrl(image?.file || image?.path || image?.image_path || image?.redraw_image);

  const file = image?.file || image?.path || image?.image_path || image?.redraw_image || image?.redraw_url;

  if ($("imageMeta")) $("imageMeta").textContent = image?.mime_type ? `mime: ${image.mime_type}` : "";
  if ($("imagePath")) $("imagePath").textContent = file ? `file: ${file}` : "";

  if (!img || !fallback) return;

  if (!url) {
    img.classList.add("hidden");
    fallback.classList.remove("hidden");
    fallback.textContent = "No image generated.";
    return;
  }

  img.src = "";
  img.removeAttribute("src");
  img.src = url;

  img.onload = () => {
    img.classList.remove("hidden");
    fallback.classList.add("hidden");
  };
  img.onerror = () => {
    img.classList.add("hidden");
    fallback.classList.remove("hidden");
    fallback.textContent = `Image failed to load: ${url}`;
  };
}

function renderQuickStats(timeline) {
  const segs = safeArray(timeline?.timeline_segments);
  if ($("statSegments")) $("statSegments").textContent = String(segs.length);

  const switches = timeline?.totals?.context_switch_count ?? Math.max(0, segs.length - 1);
  if ($("statSwitches")) $("statSwitches").textContent = String(switches);

  if ($("statsMeta")) $("statsMeta").textContent = timeline?.date_local ? `date_local: ${timeline.date_local}` : "";
}

function showTab(name) {
  document.querySelectorAll(".tabPanel").forEach((p) => p.classList.add("hidden"));
  const panel = $(`tab-${name}`);
  if (panel) panel.classList.remove("hidden");

  document.querySelectorAll(".tab").forEach((t) => t.classList.add("opacity-40"));
  const btn = document.querySelector(`.tab[data-tab="${name}"]`);
  if (btn) btn.classList.remove("opacity-40");
}

function wireTabs() {
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));
  showTab("human");
}

function setCapStatusText(s) {
  const el = $("capStatusText");
  if (!el) return;
  if (!s) { el.textContent = "capture: —"; return; }

  const running = !!s.running;
  const paused = !!s.paused;
  const last = s.last_shot_ts ? String(s.last_shot_ts).replace("T", " ").slice(0, 19) : "—";

  el.textContent = running
    ? (paused ? `capture: PAUSED · last ${last}` : `capture: RUNNING · last ${last}`)
    : `capture: STOPPED · last ${last}`;
}

function setGoogleStatusText(s) {
  const el = $("googleStatusText");
  if (!el) return;
  if (!s) { el.textContent = "google: —"; return; }
  el.textContent = s.connected ? "google: CONNECTED" : "google: NOT CONNECTED";
}

async function loadForDate(dateStr) {
  if (!dateStr) throw new Error("Please select a date.");

  const timeline = await fetchJson(`/api/day/${dateStr}/timeline`);
  const report = await fetchJson(`/api/day/${dateStr}/report`);

  let feedback = null;
  try { feedback = await fetchJson(`/api/day/${dateStr}/feedback`); } catch (_) { feedback = null; }

  setTitle(dateStr);
  setThemeFromStylePreset(report?.inputs?.style_preset);
  setPills(report?.date_local, report?.timezone, report?.inputs?.style_preset);

  if ($("timelineMeta")) {
    const m = timeline?.capture_interval_minutes;
    $("timelineMeta").textContent = m ? `${m} min interval` : "";
  }

  renderReadableTimeline(timeline?.timeline_human_readable);
  renderSegments(timeline?.timeline_segments);
  renderQuickStats(timeline);

  renderVibe(report?.outputs?.vibe);
  renderImage(report?.outputs?.image);

  renderFeedback(feedback);
}

function initDefaultDate() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  if ($("dateInput")) $("dateInput").value = `${yyyy}-${mm}-${dd}`;
}

function wireStyleSelect() {
  const sel = $("styleSelect");
  if (!sel) return;
  sel.addEventListener("change", () => setThemeFromStylePreset(sel.value));
}

async function refreshCaptureStatus() {
  try { setCapStatusText(await fetchJson("/api/capture/status")); }
  catch (_) { setCapStatusText(null); }
}

async function refreshGoogleStatus() {
  try {
    const s = await fetchJson("/api/auth/google/status");
    setGoogleStatusText(s);
    if (s?.connected) loadGoogleToday(false).catch(() => {});
    else {
      if ($("googleTodayMeta")) $("googleTodayMeta").textContent = "Connect Google to view today’s events & tasks.";
    }
    return s;
  } catch (_) {
    setGoogleStatusText(null);
    return null;
  }
}

async function startCapture() {
  const s = await postJson("/api/capture/start", {});
  setCapStatusText(s);
  return s;
}

async function stopCapture() {
  const s = await postJson("/api/capture/stop", {});
  setCapStatusText(s);
  return s;
}

/* ✅ NEW: Build (latest, no redraw) */
async function buildLatestNoRedraw() {
  $("subtitle").textContent = "Building (no redraw)…";
  const out = await postJson("/api/build", {});
  $("subtitle").textContent = "Build finished.";
  if (out?.date) {
    if ($("dateInput")) $("dateInput").value = out.date;
    await loadForDate(out.date);
    loadGoogleToday(true).catch(() => {});
  }
  return out;
}

/* Build Today = with redraw */
async function buildToday() {
  $("subtitle").textContent = "Building today…";
  const out = await postJson("/api/build/today", {});
  $("subtitle").textContent = "Build finished.";
  if (out?.date) {
    if ($("dateInput")) $("dateInput").value = out.date;
    await loadForDate(out.date);
    loadGoogleToday(true).catch(() => {});
  }
  return out;
}

async function connectGoogle() {
  const out = await fetchJson("/api/auth/google/start");
  if (!out?.auth_url) throw new Error("Missing auth_url from server.");
  window.location.href = out.auth_url;
}

async function disconnectGoogle() {
  const out = await postJson("/api/auth/google/disconnect", {});
  await refreshGoogleStatus();
  return out;
}

function main() {
  wireTabs();
  initDefaultDate();
  wireStyleSelect();

  if ($("capStartBtn")) $("capStartBtn").addEventListener("click", async () => {
    try { showToast("Starting capture…", "loading", 1800); await startCapture(); showToast("Capture started.", "success", 2200); }
    catch (e) { showToast(e.message || String(e), "error", 3800); }
  });

  if ($("capStopBtn")) $("capStopBtn").addEventListener("click", async () => {
    try { showToast("Stopping capture…", "loading", 1800); await stopCapture(); showToast("Capture stopped.", "success", 2200); }
    catch (e) { showToast(e.message || String(e), "error", 3800); }
  });

  /* ✅ Build button (latest, no redraw) */
  if ($("buildBtn")) $("buildBtn").addEventListener("click", async () => {
    try { showToast("Building latest (no redraw)…", "loading", 2500); await buildLatestNoRedraw(); showToast("Build finished.", "success", 2500); }
    catch (e) { showToast(e.message || String(e), "error", 4500); $("subtitle").textContent = "Build failed."; }
  });

  if ($("buildTodayBtn")) $("buildTodayBtn").addEventListener("click", async () => {
    try { showToast("Building today’s artifacts…", "loading", 2500); await buildToday(); showToast("Build finished.", "success", 2500); }
    catch (e) { showToast(e.message || String(e), "error", 4500); $("subtitle").textContent = "Build failed."; }
  });

  if ($("googleConnectBtn")) $("googleConnectBtn").addEventListener("click", async () => {
    try { showToast("Opening Google sign-in…", "loading", 2000); await connectGoogle(); }
    catch (e) { showToast(e.message || String(e), "error", 4500); }
  });

  if ($("googleDisconnectBtn")) $("googleDisconnectBtn").addEventListener("click", async () => {
    try { showToast("Disconnecting Google…", "loading", 1800); await disconnectGoogle(); showToast("Google disconnected.", "success", 2500); }
    catch (e) { showToast(e.message || String(e), "error", 4500); }
  });

  if ($("googleTodayRefreshBtn")) $("googleTodayRefreshBtn").addEventListener("click", async () => {
    try { showToast("Refreshing Google Today…", "loading", 1800); await loadGoogleToday(true); showToast("Google Today refreshed.", "success", 2200); }
    catch (e) { showToast(e.message || String(e), "error", 4200); }
  });

  const loadBtn = $("loadBtn");
  if (loadBtn) {
    loadBtn.addEventListener("click", async () => {
      try {
        $("subtitle").textContent = "Loading…";
        await loadForDate($("dateInput").value);
        $("subtitle").textContent = "Loaded.";
        showToast("Loaded.", "success", 1600);
        loadGoogleToday(true).catch(() => {});
      } catch (e) {
        $("subtitle").textContent = "Load failed.";
        showToast(e.message || String(e), "error", 4200);
      }
    });
  }

  // Privacy buttons
  if ($("privacyReloadBtn")) $("privacyReloadBtn").addEventListener("click", async () => {
    try { showToast("Reloading blacklist…", "loading", 1800); await loadPrivacyConfig(); showToast("Blacklist loaded.", "success", 2200); }
    catch (e) { showToast(e.message || String(e), "error", 4200); }
  });

  if ($("privacySaveBtn")) $("privacySaveBtn").addEventListener("click", async () => {
    try { showToast("Saving blacklist…", "loading", 2000); await savePrivacyConfig(); showToast("Saved.", "success", 2500); }
    catch (e) { showToast(e.message || String(e), "error", 4200); }
  });

  if ($("addAppBtn")) $("addAppBtn").addEventListener("click", () => {
    const v = $("addAppInput")?.value || "";
    const r = addOne("app", v);
    if (r.ok) { $("addAppInput").value = ""; showToast("App added (not saved yet). Click Save.", "success", 2200); }
    else { showToast(r.reason === "exists" ? "Already exists." : "Empty.", "error", 2200); }
  });

  if ($("addKeywordBtn")) $("addKeywordBtn").addEventListener("click", () => {
    const v = $("addKeywordInput")?.value || "";
    const r = addOne("keyword", v);
    if (r.ok) { $("addKeywordInput").value = ""; showToast("Keyword added (not saved yet). Click Save.", "success", 2200); }
    else { showToast(r.reason === "exists" ? "Already exists." : "Empty.", "error", 2200); }
  });

  if ($("addAppInput")) $("addAppInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); $("addAppBtn")?.click(); }
  });
  if ($("addKeywordInput")) $("addKeywordInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); $("addKeywordBtn")?.click(); }
  });

  if ($("blockedAppsInput")) $("blockedAppsInput").addEventListener("input", () => { readStateFromTextareas(); renderPrivacyUI(); });
  if ($("blockedKeywordsInput")) $("blockedKeywordsInput").addEventListener("input", () => { readStateFromTextareas(); renderPrivacyUI(); });

  refreshCaptureStatus();
  refreshGoogleStatus();
  setInterval(refreshCaptureStatus, 2000);
  setInterval(refreshGoogleStatus, 2500);

  loadPrivacyConfig().catch(() => {});
  setTimeout(() => {
    loadForDate($("dateInput").value).catch(() => {});
    loadGoogleToday(false).catch(() => {});
  }, 150);
}

main();
