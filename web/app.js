function $(id){ return document.getElementById(id); }

function formatVibeLabel(v){
  const map = {
    hurried_anxious: "Hurried / Anxious",
    calm_relaxed: "Calm / Relaxed",
    creative_flow: "Creative Flow",
    deep_focus: "Deep Focus",
    distracted_scattered: "Distracted",
    social_connected: "Social / Connected",
    learning_mode: "Learning Mode",
    mixed_unclear: "Mixed / Unclear"
  };
  return map[v] || v || "—";
}

function safeArray(x){ return Array.isArray(x) ? x : []; }
function safeText(x){ return (typeof x === "string") ? x : ""; }

function setPills(dateLocal, timezone, stylePreset){
  const row = $("pillRow");
  row.innerHTML = "";

  const pills = [
    { k: "Date", v: dateLocal || "—" },
    { k: "TZ", v: timezone || "—" },
    { k: "Style", v: stylePreset || "—" }
  ];

  for(const p of pills){
    const el = document.createElement("div");
    el.className = "pill";
    el.innerHTML = `<b>${p.k}:</b> ${p.v}`;
    row.appendChild(el);
  }
}

function renderReadableTimeline(lines){
  const wrap = $("timelineReadable");
  wrap.innerHTML = "";
  const arr = safeArray(lines);

  if(arr.length === 0){
    wrap.innerHTML = `<div class="row"><div class="row__text">No timeline_human_readable found.</div></div>`;
    return;
  }

  for(const line of arr){
    const r = document.createElement("div");
    r.className = "row";

    // Attempt to split "08:00–09:00  X | Y (confidence: 0.92)"
    const m = safeText(line).match(/^(\d{2}:\d{2}–\d{2}:\d{2})\s+(.*)$/);
    const timePart = m ? m[1] : "";
    const textPart = m ? m[2] : safeText(line);

    r.innerHTML = `
      <div class="row__time">${timePart || ""}</div>
      <div class="row__text">${escapeHtml(textPart)}</div>
    `;
    wrap.appendChild(r);
  }
}

function renderSegments(segments){
  const wrap = $("timelineSegments");
  wrap.innerHTML = "";
  const arr = safeArray(segments);

  if(arr.length === 0){
    wrap.innerHTML = `<div class="row"><div class="row__text">No timeline_segments found.</div></div>`;
    return;
  }

  for(const seg of arr){
    const id = safeText(seg.segment_id);
    const st = safeText(seg.start_time_local);
    const et = safeText(seg.end_time_local);
    const dom = safeText(seg.dominant_surface);
    const act = safeText(seg.activity);
    const dur = seg.duration_minutes ?? "—";
    const conf = (typeof seg.confidence === "number") ? seg.confidence.toFixed(2) : "—";

    const context = safeText(seg.context_detail);
    const notes = safeText(seg.notes);

    const supports = safeArray(seg.supporting_surfaces);
    const evidence = safeArray(seg.evidence_frames);
    const flags = safeArray(seg.risk_flags);

    const el = document.createElement("div");
    el.className = "seg";
    el.innerHTML = `
      <div class="seg__top">
        <div class="seg__left">
          <div class="seg__title">${escapeHtml(st)}–${escapeHtml(et)} · ${escapeHtml(dom)}</div>
          <div class="seg__sub">${escapeHtml(act)} · ${escapeHtml(String(dur))} min · conf ${escapeHtml(conf)}</div>
        </div>
        <div class="seg__badge">${escapeHtml(id || "SEG")}</div>
      </div>
      <div class="seg__more">
        ${context ? `<div><b>Context:</b> ${escapeHtml(context)}</div>` : ""}
        ${notes ? `<div style="margin-top:6px;"><b>Notes:</b> ${escapeHtml(notes)}</div>` : ""}
        <div class="seg__chips">
          ${supports.map(s => `<div class="chip">support: ${escapeHtml(s)}</div>`).join("")}
          ${flags.filter(f=>f && f!=="none").map(f => `<div class="chip">flag: ${escapeHtml(f)}</div>`).join("")}
          ${evidence.slice(0,6).map(f => `<div class="chip">frame: ${escapeHtml(f)}</div>`).join("")}
          ${evidence.length > 6 ? `<div class="chip">+${evidence.length - 6} more</div>` : ""}
        </div>
      </div>
    `;
    wrap.appendChild(el);
  }
}

function renderVibe(vibe){
  const pv = safeText(vibe.primary_vibe);
  const conf = (typeof vibe.confidence === "number") ? vibe.confidence.toFixed(2) : "—";

  $("vibeBadge").textContent = formatVibeLabel(pv);
  $("vibeConf").textContent = `confidence ${conf}`;

  const why = safeArray(vibe.why);
  const patterns = safeArray(vibe.notable_patterns);

  $("vibeWhy").innerHTML = why.length ? why.map(x=>`<li>${escapeHtml(String(x))}</li>`).join("") : "<li>—</li>";
  $("vibePatterns").innerHTML = patterns.length ? patterns.map(x=>`<li>${escapeHtml(String(x))}</li>`).join("") : "<li>—</li>";

  $("caringMessage").textContent = safeText(vibe.caring_message) || "—";
  $("quote").textContent = safeText(vibe.quote) || "—";
  $("humorAlt").textContent = safeText(vibe.humor_alt) || "—";

  $("vibeMeta").textContent = pv ? `primary_vibe: ${pv}` : "—";
}

function renderImage(imageInfo){
  const imgEl = $("redrawImg");
  const fallback = $("imageFallback");

  const file = safeText(imageInfo.file);
  const mime = safeText(imageInfo.mime_type);

  $("imageMeta").textContent = mime ? mime : "—";
  $("imagePath").textContent = file || "—";

  if(!file){
    imgEl.style.display = "none";
    fallback.style.display = "grid";
    return;
  }

  // Support two patterns:
  // 1) Absolute path in JSON: not fetchable by browser directly
  // 2) Relative path you host together with the web folder
  //
  // Best practice: copy redraw image into web/assets OR run server at repo root and use relative url
  const url = toBrowserPath(file);

  imgEl.onload = () => {
    imgEl.style.display = "block";
    fallback.style.display = "none";
  };
  imgEl.onerror = () => {
    imgEl.style.display = "none";
    fallback.style.display = "grid";
    fallback.textContent = "Image path not accessible from browser. Use a local server and relative paths.";
  };
  imgEl.src = url;
}

function toBrowserPath(p){
    if(!p) return "";
    const norm = p.replaceAll("\\", "/");
  
    // URL 原样返回
    if(norm.startsWith("http://") || norm.startsWith("https://")) return norm;
  
    // 如果已经是以 / 开头的 root-relative，直接用
    if(norm.startsWith("/")) return norm;
  
    // 如果是我们项目里的资源路径，强制从站点根目录取
    // 关键：避免在 /web/ 下被解析成 /web/screenshots...
    if(norm.startsWith("screenshots/") || norm.startsWith("screenshots_test/")){
      return "/" + norm;
    }
  
    // 兼容：从路径中截出 screenshots 之后的部分
    const idx1 = norm.indexOf("/screenshots/");
    if(idx1 >= 0) return "/" + norm.slice(idx1 + 1);
  
    const idx2 = norm.indexOf("/screenshots_test/");
    if(idx2 >= 0) return "/" + norm.slice(idx2 + 1);
  
    // 其他情况按相对路径处理（不推荐）
    return norm;
  }

function renderTotals(totals){
  const bySurface = safeArray(totals.by_surface_minutes);
  const byActivity = safeArray(totals.by_activity_minutes);

  $("totalsMeta").textContent = `switches: ${totals.context_switch_count ?? "—"}`;

  renderBars("bySurface", bySurface.map(x => ({
    name: x.surface,
    value: x.minutes
  })));

  renderBars("byActivity", byActivity.map(x => ({
    name: x.activity,
    value: x.minutes
  })));
}

function renderBars(containerId, items){
  const wrap = $(containerId);
  wrap.innerHTML = "";

  const arr = safeArray(items);
  if(arr.length === 0){
    wrap.innerHTML = `<div class="row"><div class="row__text">—</div></div>`;
    return;
  }

  const maxVal = Math.max(...arr.map(x => Number(x.value || 0)), 1);

  for(const it of arr.slice(0, 12)){
    const name = safeText(it.name) || "—";
    const val = Number(it.value || 0);
    const pct = Math.round((val / maxVal) * 100);

    const el = document.createElement("div");
    el.className = "bar";
    el.innerHTML = `
      <div class="bar__top">
        <div class="bar__name">${escapeHtml(name)}</div>
        <div class="bar__val">${escapeHtml(String(val))} min</div>
      </div>
      <div class="bar__track">
        <div class="bar__fill" style="width:${pct}%"></div>
      </div>
    `;
    wrap.appendChild(el);
  }
}

function renderQuickStats(timelineJson, reportJson){
  const segs = safeArray(timelineJson.timeline_segments);
  const totals = timelineJson.totals || {};

  $("statSegments").textContent = String(segs.length || 0);
  $("statSwitches").textContent = String(totals.context_switch_count ?? Math.max(0, segs.length - 1));

  const topSurface = safeArray(totals.by_surface_minutes)[0]?.surface || "—";
  const topActivity = safeArray(totals.by_activity_minutes)[0]?.activity || "—";

  $("statTopSurface").textContent = topSurface;
  $("statTopActivity").textContent = topActivity;

  const dateLocal = reportJson?.date_local || timelineJson?.date_local || "—";
  $("statsMeta").textContent = dateLocal;
}

function setTitle(dateLocal){
  $("title").textContent = dateLocal ? `Daily Recap · ${dateLocal}` : "Daily Recap";
}

function wireTabs(){
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach(t => {
    t.addEventListener("click", () => {
      tabs.forEach(x => x.classList.remove("isActive"));
      t.classList.add("isActive");

      const name = t.getAttribute("data-tab");
      document.querySelectorAll(".tabPanel").forEach(p => p.classList.remove("isActive"));
      const panel = document.getElementById(`tab-${name}`);
      if(panel) panel.classList.add("isActive");
    });
  });
}

function escapeHtml(str){
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJson(path){
  const res = await fetch(path, { cache: "no-store" });
  if(!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  return await res.json();
}

function getDateFromInput(){
  const v = $("dateInput").value;
  return v || "";
}

function toDayFolder(dateStr){
    // Expect YYYY-MM-DD
    const [y, m, d] = dateStr.split("-");
    if(!y || !m || !d) return "";
    const monthName = monthNumberToName(m);
    return `../screenshots_test/${y}/${monthName}/${d}`;
  }

function monthNumberToName(mm){
  const map = {
    "01":"January","02":"February","03":"March","04":"April","05":"May","06":"June",
    "07":"July","08":"August","09":"September","10":"October","11":"November","12":"December"
  };
  return map[mm] || "January";
}

async function loadForDate(dateStr){
  if(!dateStr){
    alert("Please select a date first.");
    return;
  }

  const folder = toDayFolder(dateStr);
  const reportPath = `${folder}/daily_report_${dateStr}.json`;
  const timelinePath = `${folder}/timeline_${dateStr}.json`;

  const reportJson = await fetchJson(reportPath);
  const timelineJson = await fetchJson(timelinePath);

  setTitle(dateStr);
  setPills(reportJson.date_local, reportJson.timezone, reportJson.inputs?.style_preset);

  $("timelineMeta").textContent = `${timelineJson.capture_interval_minutes ?? "—"} min interval`;
  renderReadableTimeline(timelineJson.timeline_human_readable);
  renderSegments(timelineJson.timeline_segments);

  renderVibe(reportJson.outputs?.vibe || {});
  renderImage(reportJson.outputs?.image || {});
  renderTotals(timelineJson.totals || {});
  renderQuickStats(timelineJson, reportJson);
}

function initDefaultDate(){
  const today = new Date();
  const yyyy = String(today.getFullYear());
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  $("dateInput").value = `${yyyy}-${mm}-${dd}`;
}

function main(){
  wireTabs();
  initDefaultDate();

  $("loadBtn").addEventListener("click", async () => {
    try{
      await loadForDate(getDateFromInput());
    }catch(e){
      console.error(e);
      alert(String(e.message || e));
    }
  });

  // Auto-load on first open (best-effort)
  setTimeout(async () => {
    try{
      await loadForDate(getDateFromInput());
    }catch(e){
      // ignore auto-load failure (usually due to missing files/server)
      console.log("Auto-load skipped:", e);
    }
  }, 150);
}

main();
