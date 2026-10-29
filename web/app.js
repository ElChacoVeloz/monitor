/* Monitor — tema LCARS. Mismo contrato que el front original: lee /api/data cada
   60 s, reloj cada segundo, escala 1920x1080, recarga sola cuando cambia `version`,
   slot rotativo sol/alerta/ruta, radar centrado en la casa, lista medida. */

const $ = (id) => document.getElementById(id);
const API = "/api/data";

/* ─────────────────────────── iconos (trazo, monocromo) ─────────────────────────── */
const SUN_RAYS = `<path d="M12 2.4v2.3M12 19.3v2.3M2.4 12h2.3M19.3 12h2.3M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6"/>`;
const CLOUD = `<path d="M7.2 18.4h9.4a3.7 3.7 0 0 0 .4-7.4 5.3 5.3 0 0 0-10.1-1.1 4 4 0 0 0 .3 8.5z"/>`;
const ICONS = {
  clear: `<circle cx="12" cy="12" r="4.15"/>${SUN_RAYS}`,
  "mostly-clear": `<circle cx="12" cy="11.4" r="4.4"/><path d="M12 2.5v2M3.4 12h2M5.9 5.9l1.4 1.4M18.1 5.9l-1.4 1.4M19.1 12h1.4"/>`,
  "partly-cloudy": `<circle cx="8.6" cy="7.9" r="3"/><path d="M8.6 2.6v1.6M3.3 7.9h1.6M4.9 4.2l1.1 1.1M12.3 4.2l-1.1 1.1"/>${CLOUD}`,
  cloudy: CLOUD,
  fog: `${CLOUD}<path d="M6.6 20.4h10.8M8.4 22.3h7.2"/>`,
  drizzle: `${CLOUD}<path d="M8.6 20.2l-.6 1.7M12 20.2l-.6 1.7M15.4 20.2l-.6 1.7"/>`,
  rain: `${CLOUD}<path d="M8.4 19.8l-1.1 3M12 19.8l-1.1 3M15.6 19.8l-1.1 3"/>`,
  showers: `${CLOUD}<path d="M7.8 19.9l-1.5 3.1M11.4 19.9l-1.5 3.1M15 19.9l-1.5 3.1M18.2 19.9l-1 2"/>`,
  sleet: `${CLOUD}<path d="M8.6 20l-1 2.9M12 20v3M15.4 20l1 2.9"/>`,
  snow: `${CLOUD}<path d="M8.2 20.6v2.6M7 21.9h2.4M15.8 20.6v2.6M14.6 21.9h2.4"/>`,
  thunder: `${CLOUD}<path d="M13.2 19.2l-3 4.2h3l-1.6 3"/>`,
  "night-clear": `<path d="M20.4 14.6A8.6 8.6 0 1 1 9.6 3.8a6.7 6.7 0 0 0 10.8 10.8z"/>`,
  "night-partly": `<path d="M15.6 3.9a5.6 5.6 0 0 0-2 9.1 3.7 3.7 0 0 0-.4-.1 5.3 5.3 0 0 0-10 1.1 4 4 0 0 0 .3 8.5h9.4a3.7 3.7 0 0 0 .4-7.4 5.6 5.6 0 0 0 2.3-11.2z"/>`,
};
function iconSvg(name, isDay) {
  let k = name || "cloudy";
  if (k === "clear-day") k = "clear";
  if (!isDay) {
    if (k === "clear" || k === "mostly-clear") k = "night-clear";
    else if (k === "partly-cloudy") k = "night-partly";
  }
  if (!ICONS[k]) k = "cloudy";
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55"
    stroke-linecap="round" stroke-linejoin="round">${ICONS[k]}</svg>`;
}

/* ─────────────────────────────── estado ─────────────────────────────── */
let DATA = null;
let TZ = "America/Chicago";
let VERSION = null;

const fmtCache = new Map();
function fmt(opts) {
  const key = JSON.stringify(opts);
  if (!fmtCache.has(key)) fmtCache.set(key, new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts }));
  return fmtCache.get(key);
}
const hm = (d) => fmt({ hour: "numeric", minute: "2-digit", hour12: true }).format(d);

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const srcError = (name) => (DATA && DATA.sources && DATA.sources[name] && DATA.sources[name].error) || "";

/* escala 1920x1080 a cualquier pantalla */
function fit() {
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  $("screen").style.transform = `scale(${s})`;
}
window.addEventListener("resize", fit);

/* LCARS es oscuro siempre; la clase day/night se conserva para el arranque
   (localStorage) y para que ?theme= siga funcionando igual que en el original */
function applyTheme() {
  const sun = DATA && DATA.weather && DATA.weather.sun;
  const now = new Date();
  let rise = sun && sun.sunrise ? new Date(sun.sunrise) : null;
  let set = sun && sun.sunset ? new Date(sun.sunset) : null;
  if (!rise || isNaN(rise) || !set || isNaN(set)) {
    rise = new Date(now); rise.setHours(7, 0, 0, 0);
    set = new Date(now); set.setHours(19, 0, 0, 0);
  }
  let isDay = now >= rise && now < set;
  const forced = (new URLSearchParams(location.search).get("theme") || "").toLowerCase();
  if (forced === "day") isDay = true;
  if (forced === "night") isDay = false;
  const root = document.documentElement;
  root.classList.remove("booting", "day", "night");
  root.classList.add(isDay ? "day" : "night");
  try { localStorage.setItem("monitor.theme", isDay ? "day" : "night"); } catch (e) {}
}

/* ─────────────────────────────── color ─────────────────────────────── */
function hexRgb(hex) {
  const h = String(hex || "#5b8def").replace("#", "");
  const s = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(s.slice(0, 6), 16);
  if (isNaN(n)) return [91, 141, 239];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
/* la píldora lleva texto negro: el color del calendario se aclara ~42 % hacia
   blanco (igual que el LCARS del iPad). El tono es decisión del Capitán: no se
   re-mapea a la paleta, solo se aclara. */
function pillColor(hex) {
  const [r, g, b] = hexRgb(hex);
  const m = (c) => Math.round(c + (255 - c) * 0.42);
  return `rgb(${m(r)},${m(g)},${m(b)})`;
}

/* ─────────────────────────────── arriba ─────────────────────────────── */
function renderClock() {
  const now = new Date();
  const [time, ampm] = hm(now).split(" ");
  $("clockTime").textContent = time;
  $("clockAmPm").textContent = ampm || "";
  $("dateLong").textContent = fmt({ weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(now);
  const y = Number(fmt({ year: "numeric" }).format(now));
  const ymd = fmt({ year: "numeric", month: "2-digit", day: "2-digit" }).format(now).split("/");
  const doy = Math.round((Date.UTC(y, Number(ymd[0]) - 1, Number(ymd[1])) - Date.UTC(y, 0, 1)) / 86400000) + 1;
  $("stardate").textContent = `DAY ${String(doy).padStart(3, "0")} · ${y}`;
}

function renderNow() {
  const w = DATA.weather;
  if (!w) {
    $("nowIcon").innerHTML = "";
    $("nowTemp").textContent = "--";
    $("nowDesc").textContent = "Weather unavailable";
    $("nowFeels").textContent = srcError("weather");
    $("nowExtra").textContent = "";
    return;
  }
  const cur = w.current;
  $("nowIcon").innerHTML = iconSvg(cur.icon, cur.isDay);
  $("nowTemp").textContent = Math.round(cur.tempC);
  $("nowDesc").textContent = cur.desc + (DATA.sources.weather && DATA.sources.weather.stale ? " · cached" : "");
  $("nowFeels").textContent = `Feels like ${Math.round(cur.feelsC)}°C`;
  $("nowExtra").textContent = `${cur.humidity}% hum · wind ${Math.round(cur.windKph)} km/h`;
}

function renderForecast() {
  const box = $("forecast");
  const w = DATA.weather;
  if (!w || !w.daily || !w.daily.length) { box.innerHTML = ""; return; }
  const n = (DATA.config.week.forecastDays || 5);
  const startsToday = DATA.config.week.forecastStartsToday !== false;
  const off = startsToday ? 0 : 1;
  box.innerHTML = w.daily.slice(off, off + n).map((d, i) => {
    const dt = new Date(`${d.date}T12:00:00`);
    const label = startsToday && i === 0 ? "Today" : fmt({ weekday: "short" }).format(dt);
    const rain = d.rainPct;
    return `<div class="fday ${startsToday && i === 0 ? "today" : ""}">
      <div class="flabel">${label}</div>
      <div class="ficon">${iconSvg(d.icon, true)}</div>
      <div class="ftemps"><span class="fhi">${Math.round(d.maxC)}°</span><span class="flo">${Math.round(d.minC)}°</span></div>
      <div class="frain ${rain ? "" : "off"}">${rain == null ? "--" : `RAIN ${rain}%`}</div>
    </div>`;
  }).join("");
}

/* barra lateral: datos reales del payload, no decoración */
function renderSide() {
  const w = DATA.weather || {};
  const cur = w.current || {};
  const today = (w.daily && w.daily[0]) || {};
  const r = (v, u) => (v == null ? "—" : `${Math.round(v)}${u || ""}`);
  let dayLen = "—";
  if (w.sun && w.sun.sunrise && w.sun.sunset) {
    const mins = Math.round((new Date(w.sun.sunset) - new Date(w.sun.sunrise)) / 60000);
    if (mins > 0) dayLen = `${Math.floor(mins / 60)}H ${String(mins % 60).padStart(2, "0")}M`;
  }
  const blocks = [
    ["s-org", "high / low °C", `${r(today.maxC, "°")} / ${r(today.minC, "°")}`],
    ["s-pch", "feels like", r(cur.feelsC, "°C")],
    ["s-lav", "humidity", r(cur.humidity, "%")],
    ["s-gry", "wind km/h", r(cur.windKph)],
    ["s-sal", "rain today", r(today.rainPct, "%")],
    ["s-lav", "daylight", dayLen],
    ["s-gry grow", "", ""],
  ];
  $("side").innerHTML = blocks.map(([c, k, v]) =>
    `<div class="blk ${c}">${k ? `<span class="k">${escapeHtml(k)}</span>` : ""}${
      v ? `<span class="v">${escapeHtml(v)}</span>` : ""}</div>`).join("");
}

/* ─────────────────────────────── semana ─────────────────────────────── */
/* mismo evento en dos calendarios = UNA píldora con los dos colores */
function mergeDuplicateEvents(evs) {
  const out = [];
  const seen = new Map();
  for (const ev of evs) {
    const key = [ev.allDay ? "1" : "0", ev.start || "", ev.end || "",
                 (ev.title || "").trim().toLowerCase()].join("|");
    const prev = seen.get(key);
    if (!prev) {
      const merged = { ...ev, colors: ev.color ? [ev.color] : [], cals: ev.calendar ? [ev.calendar] : [] };
      seen.set(key, merged);
      out.push(merged);
    } else {
      if (ev.color && !prev.colors.includes(ev.color)) prev.colors.push(ev.color);
      if (ev.calendar && !prev.cals.includes(ev.calendar)) prev.cals.push(ev.calendar);
      if (!prev.location && ev.location) prev.location = ev.location;
    }
  }
  return out;
}

function eventTime(ev) {
  if (ev.allDay) return "All day";
  const d = new Date(ev.start);
  return isNaN(d) ? "" : hm(d);
}

function offlineBox(text, reason) {
  return `<div class="offline"><div><div class="offtitle">${escapeHtml(text)}</div>
    ${reason ? `<div class="offreason">${escapeHtml(reason)}</div>` : ""}</div></div>`;
}

function renderWeek() {
  const box = $("week");
  const cal = DATA.calendar;
  const note = $("weekNote");
  note.classList.remove("warn");
  if (!cal || !cal.days) {
    box.classList.add("weekoff");
    box.innerHTML = offlineBox("Calendar is not available right now", srcError("calendar"));
    note.textContent = "OFFLINE";
    note.classList.add("warn");
    return;
  }
  box.classList.remove("weekoff");
  if (cal.unconfigured) {
    box.classList.add("weekoff");
    box.innerHTML = offlineBox("No calendars yet", "run calendar-config.py add-missing on the server");
    note.textContent = "";
    return;
  }
  box.innerHTML = cal.days.map((day, i) => {
    const dt = new Date(`${day.date}T12:00:00`);
    const label = i === 0 ? "Today" : i === 1 ? "Tomorrow" : fmt({ weekday: "long" }).format(dt);
    const num = fmt({ day: "numeric" }).format(dt);
    const mon = fmt({ month: "short" }).format(dt);
    const evs = mergeDuplicateEvents(day.events || []);
    const cards = evs.map((ev) => {
      const cols = (ev.colors.length ? ev.colors : [ev.color]).map(pillColor);
      const dual = cols.length > 1;
      return `<div class="evt ${ev.allDay ? "allday" : ""} ${dual ? "dual" : ""}" style="--ev2:${cols[1] || cols[0]}">
        <div class="etime" style="background:${cols[0]}">${eventTime(ev)}</div>
        <div class="etitle">${escapeHtml(ev.title)}</div>
        ${ev.location && !ev.allDay ? `<div class="eloc">${escapeHtml(ev.location)}</div>` : ""}
      </div>`;
    }).join("");
    return `<div class="daycol ${i === 0 ? "today" : ""}" data-day="${i}">
      <div class="dayhead">
        <div class="daynum">${num}</div>
        <div class="dayname">${label}</div>
        <div class="daysub">${mon}</div>
      </div>
      <div class="events" data-day="${i}">${cards || `<div class="empty">— NO EVENTS —</div>`}</div>
    </div>`;
  }).join("");

  /* nada de recorte silencioso: se mide y lo que no cabe se anuncia */
  box.querySelectorAll(".events").forEach((col) => {
    const day = box.querySelector(`.daycol[data-day="${col.dataset.day}"]`);
    const cards = [...col.querySelectorAll(".evt")];
    if (cards.length > 0 && cards.length <= 3) day.classList.add("sparse");
    const fits = () => col.scrollHeight <= col.clientHeight + 2;
    if (!fits()) { day.classList.remove("sparse"); day.classList.add("dense"); }
    if (!fits()) {
      const more = document.createElement("div");
      more.className = "more";
      col.appendChild(more);           // se reserva su alto ANTES de medir
      let hidden = 0;
      while (!fits() && cards.length - hidden > 1) {
        cards[cards.length - 1 - hidden].style.display = "none";
        hidden++;
        more.textContent = `+${hidden} more`;
      }
      if (!hidden) more.remove();
    }
  });

  const bits = [];
  if (cal.placeholder) bits.push("demo data");
  if (cal.range) {
    const a = new Date(`${cal.range.start}T12:00:00`), b = new Date(`${cal.range.end}T12:00:00`);
    bits.push(`${fmt({ month: "short", day: "numeric" }).format(a)} – ${fmt({ month: "short", day: "numeric" }).format(b)}`);
  }
  if (cal.errors && cal.errors.length) {
    bits.push(`${cal.errors.length} feed${cal.errors.length === 1 ? "" : "s"} down: ${cal.errors.map((e) => e.calendar).join(", ")}`);
    note.classList.add("warn");
  }
  note.textContent = bits.join(" · ");
}

/* ──────────── slot de abajo a la izquierda: sol / alerta / ruta ──────────── */
function hhmmInTZ(d) { return fmt({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(d); }
function weekdayInTZ(d) {
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(fmt({ weekday: "short" }).format(d));
}
/* ?now=HH:MM o ?now=AAAA-MM-DDTHH:MM fuerza la hora del slot (pruebas) */
function slotNow() {
  const forced = new URLSearchParams(location.search).get("now");
  const now = new Date();
  if (!forced) return now;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(forced)) { const d = new Date(forced); if (!isNaN(d)) return d; }
  if (/^\d{1,2}:\d{2}$/.test(forced)) { const [h, m] = forced.split(":").map(Number); now.setHours(h, m, 0, 0); }
  return now;
}
const URGENT_SEV = { Extreme: true, Severe: true };
function slotState() {
  const forced = new URLSearchParams(location.search).get("slot");
  if (forced) return { kind: forced === "alert" ? "alerts" : forced };
  const cfg = (DATA.config && DATA.config.slot) || {};
  const now = slotNow();
  const t = hhmmInTZ(now);
  const wd = weekdayInTZ(now);
  const isWeekday = wd >= 1 && wd <= 5;
  /* 0) una alerta Severe/Extreme va hasta adelante de todo: no rota con el sol
     ni cede ante la ruta de la escuela (el server ordena items por severidad) */
  const worst = DATA.alerts && DATA.alerts.items && DATA.alerts.items[0];
  if (worst && URGENT_SEV[worst.severity]) return { kind: "alerts", urgent: true };
  /* 1) la ruta manda en sus ventanas (L-V) */
  for (const w of (cfg.routeWindows || [])) {
    if (DATA.route && (!cfg.routeWeekdaysOnly || isWeekday) && t >= w.start && t < w.end) {
      return { kind: "route", window: w };
    }
  }
  if (DATA.alerts && DATA.alerts.count > 0) {
    const rotate = (cfg.rotateSeconds || 300) * 1000;
    return { kind: Math.floor(now.getTime() / rotate) % 2 === 0 ? "alerts" : "sun" };
  }
  return { kind: "sun" };
}

const head = (cls, name, badge, badgeCls) => `<div class="pill-head">
  <span class="ph-cap ${cls}"></span><span class="ph-name ${cls}">${name}</span>
  <span class="ph-fill"></span>${badge ? `<span class="ph-badge ${badgeCls || ""}">${badge}</span>` : ""}<span class="ph-end ${cls}"></span></div>`;

function sunCard() {
  const w = DATA.weather;
  if (!w || !w.sun || !w.sun.sunrise) return head("s-lav", "SUN") + `<div class="pbody">${offlineBox("Sun times unavailable")}</div>`;
  const split = (iso) => { const d = new Date(iso); return isNaN(d) ? ["--", ""] : hm(d).split(" "); };
  const [rt, ra] = split(w.sun.sunrise), [st, sa] = split(w.sun.sunset);
  const now = new Date(), set = new Date(w.sun.sunset), rise = new Date(w.sun.sunrise);
  let foot = "";
  const mins = (a, b) => Math.max(0, Math.round((b - a) / 60000));
  const hmTxt = (m) => `${Math.floor(m / 60)}H ${String(m % 60).padStart(2, "0")}M`;
  if (now < rise) foot = `Sunrise in ${hmTxt(mins(now, rise))}`;
  else if (now < set) foot = `Sunset in ${hmTxt(mins(now, set))}`;
  else foot = "Sun is down";
  return head("s-lav", "SUN · HOUSTON") + `<div class="pbody">
    <div class="sunrow"><div class="sk s-pch">SUNRISE</div><div class="sv">${rt}<i>${ra}</i></div></div>
    <div class="sunrow set"><div class="sk s-lav">SUNSET</div><div class="sv">${st}<i>${sa}</i></div></div>
    <div class="daylen">${foot}</div></div>`;
}

const SEV = { Extreme: "sev-extreme", Severe: "sev-severe", Moderate: "sev-moderate", Minor: "sev-minor" };
function alertCard() {
  const a = DATA.alerts;
  const main = a.items && a.items[0];
  if (!main) return sunCard();
  let ends = main.area || "";
  if (main.ends) {
    const e = new Date(main.ends);
    const key = (d) => fmt({ year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
    ends = key(e) === key(new Date()) ? `Ends ${hm(e)}` : `Until ${fmt({ weekday: "short" }).format(e)} ${hm(e)}`;
  }
  if (a.count > 1) ends += ` · +${a.count - 1} more`;
  let body = (main.headline || "").trim();
  const name = (main.event || "").trim();
  if (name && body.toLowerCase().startsWith(name.toLowerCase())) {
    body = body.slice(name.length).replace(/^[\s,:–-]+/, "");
    body = body.charAt(0).toUpperCase() + body.slice(1);
  }
  return head("a-col", a.count > 1 ? `RED ALERT · ${a.count}` : "RED ALERT") + `<div class="pbody">
    <div class="alevent ${SEV[main.severity] || "sev-unknown"}">${escapeHtml(main.event)}</div>
    <div class="alhead">${escapeHtml(body || main.area || "")}</div>
    <div class="alfoot">${escapeHtml(ends)}</div></div>`;
}

function routeCard(win) {
  const r = DATA.route;
  const dest = String(r.destination || "School").replace(/\s*\(.*\)\s*$/, "");
  const live = r.live;
  const min = live ? live.min : r.min;
  const km = live ? live.km : r.km;
  const meta = live ? `${km} km · via ${live.via || "fastest route"}`
                    : `${km} km · baseline (no traffic)` + (win ? " · no live data" : "");
  return head("s-cyn", "ROUTE", win && win.label ? escapeHtml(win.label) : "") + `<div class="pbody">
    <div class="routemain"><div class="routemin">${min}<i>MIN</i></div>
      <span class="livechip ${live ? "" : "off"}">${live ? "LIVE" : "BASELINE"}</span></div>
    <div class="routemeta">${escapeHtml(meta)}</div>
    <div class="routefoot">${escapeHtml(dest)}</div></div>`;
}

let lastSlot = "";
function renderSlot(force) {
  const st = slotState();
  const sig = [st.kind, DATA.alerts ? DATA.alerts.count : 0,
    DATA.alerts && DATA.alerts.items[0] ? DATA.alerts.items[0].event : "",
    DATA.route ? `${DATA.route.min}/${DATA.route.km}` : "",
    st.window ? st.window.label : "", hm(new Date())].join("|");
  if (!force && sig === lastSlot) return;
  lastSlot = sig;
  const card = $("sunCard");
  card.classList.toggle("is-alert", st.kind === "alerts");
  card.classList.toggle("is-route", st.kind === "route");
  if (st.kind === "alerts" && DATA.alerts && DATA.alerts.count) card.innerHTML = alertCard();
  else if (st.kind === "route" && DATA.route) card.innerHTML = routeCard(st.window);
  else card.innerHTML = sunCard();
}

/* ─────────────────── radar del NWS (KHGX), centrado en la casa ─────────────────── */
const RADAR_URL = "https://radar.weather.gov/ridge/standard/KHGX_0.gif";
/* versión oscura que sirve el propio tablero (paleta del GIF reescrita: mapa
   oscuro, ecos de lluvia con sus colores reales). Si falla, se cae al original. */
const RADAR_DARK = "/api/radar.gif";
const RADAR_BUCKET_MS = 5 * 60 * 1000;
const RADAR_HOME = { x: 37.27, y: 43.78 };     // calibrado con marcadores del GIF
const RADAR_VIEW = { zoom: 1.8, fx: RADAR_HOME.x, fy: RADAR_HOME.y };

function placeRadar() {
  const img = $("radarImg");
  const box = img && img.parentElement;
  if (!box) return;
  const w = box.clientWidth, h = box.clientHeight;
  if (!w || !h) return;
  const s = Math.max(w / 600, h / 550) * RADAR_VIEW.zoom;
  const W = 600 * s, H = 550 * s;
  const px = (RADAR_VIEW.fx / 100) * 600, py = (RADAR_VIEW.fy / 100) * 550;
  const left = Math.min(0, Math.max(w - W, w / 2 - px * s));
  const top = Math.min(0, Math.max(h - H, h / 2 - py * s));
  Object.assign(img.style, { width: `${W}px`, height: `${H}px`, left: `${left}px`, top: `${top}px` });
  const dot = $("radarHome");
  if (dot) { dot.style.left = `${left + px * s}px`; dot.style.top = `${top + py * s}px`; }
}
window.addEventListener("resize", placeRadar);

function renderRadar() {
  const img = $("radarImg");
  const bucket = Math.floor(Date.now() / RADAR_BUCKET_MS);
  if (img.dataset.b !== String(bucket)) {
    img.dataset.b = String(bucket);
    img.dataset.fallback = "";
    img.src = `${RADAR_DARK}?t=${bucket}`;
  }
  if (!img.dataset.wired) {
    img.dataset.wired = "1";
    img.addEventListener("load", () => { img.classList.remove("failed"); placeRadar(); });
    img.addEventListener("error", () => {
      /* sin radar oscuro: el original del NWS, claro pero con dato */
      if (!img.dataset.fallback) { img.dataset.fallback = "1"; img.src = `${RADAR_URL}?t=${img.dataset.b}`; return; }
      img.classList.add("failed");
    });
  }
  const rc = (DATA.config && DATA.config.radar) || {};
  const probado = parseFloat(new URLSearchParams(location.search).get("zoom") || "");
  RADAR_VIEW.zoom = Number.isFinite(probado) && probado > 0 ? probado : (rc.zoom || 1.8);
  RADAR_VIEW.fx = rc.focusX ?? RADAR_HOME.x;
  RADAR_VIEW.fy = rc.focusY ?? RADAR_HOME.y;
  placeRadar();
  /* la hora es la del frame que publicó el NWS, no la del reloj local */
  const tag = $("radarWhen");
  const frame = DATA.radar && DATA.radar.updatedAt ? new Date(DATA.radar.updatedAt) : null;
  const when = frame && !isNaN(frame) ? frame : new Date(bucket * RADAR_BUCKET_MS);
  tag.textContent = hm(when);
  tag.className = "ph-badge" + (DATA.radar && DATA.radar.ageMinutes > 30 ? " warn" : "");
}

/* ─────────────────────────────── Nest ─────────────────────────────── */
function renderNest() {
  const card = $("nestCard");
  const n = DATA.nest;
  const src = (DATA.sources && DATA.sources.nest) || {};
  if (!n) {
    card.innerHTML = head("s-lav", "NEST · THERMOSTAT", "OFFLINE", "bad") +
      `<div class="pbody">${offlineBox("Nest not connected", srcError("nest") || "no data")}</div>`;
    return;
  }
  const MODES = { HEAT: "Heat", COOL: "Cool", HEATCOOL: "Auto", OFF: "Off", ECO: "Eco" };
  const STATUS = { HEATING: "heating", COOLING: "cooling", OFF: "idle", FAN: "fan" };
  const mode = MODES[(n.mode || "").toUpperCase()] || n.mode || "—";
  const status = STATUS[(n.status || "").toUpperCase()] || (n.status || "").toLowerCase() || "—";
  const badge = src.stale ? "STALE" : status;
  const badgeCls = src.stale ? "warn" : (status === "idle" ? "" : "on");
  const t = (v) => (v == null ? "--" : v);
  /* un dato viejo no se presenta como vivo: si la credencial murió, se dice */
  const err = src.stale && src.error
    ? `<div class="nest-err">${escapeHtml(src.error.replace(/^Google:\s*/, ""))}</div>` : "";
  card.innerHTML = head("s-lav", `NEST · ${escapeHtml(n.name || "THERMOSTAT")}`, escapeHtml(badge), badgeCls) +
    `<div class="pbody">
      <div class="nest-grid">
        <div class="nest-cell"><div class="nk">INSIDE</div><div class="nv">${t(n.ambientC)}<i>°C</i></div></div>
        <div class="nest-cell"><div class="nk">SET TO</div><div class="nv set">${t(n.targetC)}<i>°C</i></div></div>
      </div>${err}
      <div class="nest-meta">
        <div><span class="nk">HUMIDITY</span><b>${n.humidity == null ? "—" : n.humidity + "%"}</b></div>
        <div><span class="nk">MODE</span><b>${escapeHtml(mode)}</b></div>
      </div></div>`;
}

/* ─────────────────────────────── lista ─────────────────────────────── */
function renderShop() {
  const box = $("shop");
  const note = $("shopNote");
  const s = DATA.todoist;
  if (!s || !s.items) {
    box.innerHTML = offlineBox("Shopping list unavailable", srcError("todoist"));
    note.textContent = "OFFLINE";
    return;
  }
  const pinned = s.items.filter((i) => i.pinned);
  const rest = s.items.filter((i) => !i.pinned);
  const total = s.items.length;
  note.textContent = `${total} item${total === 1 ? "" : "s"}`;
  if (!total) { box.innerHTML = `<div class="shopempty">Nothing on the list.</div>`; return; }
  const row = (i) => `<div class="shopitem ${i.pinned ? "pinned" : ""}">
      <span class="${i.pinned ? "dot" : "box"}"></span><span class="txt">${escapeHtml(i.content)}</span></div>`;
  let html = "";
  if (pinned.length) html += `<div class="shoppinned">${pinned.map(row).join("")}</div>`;
  if (rest.length) html += `<div class="shopgrid">${rest.map(row).join("")}</div>`;
  box.innerHTML = html;

  /* cuántos caben se mide; lo que no cabe se dice en el encabezado */
  const colsFor = (w) => Math.max(1, Math.min(4, Math.floor((w + 26) / (260 + 26))));
  const pin = box.querySelector(".shoppinned");
  const grid = box.querySelector(".shopgrid");
  let cols = colsFor(box.clientWidth);
  if (grid) {
    const gap = 8;
    const itemH = 32;
    const avail = box.clientHeight - (grid.getBoundingClientRect().top - box.getBoundingClientRect().top) / currentScale();
    const rows = Math.max(1, Math.floor((avail + gap) / (itemH + gap)));
    while (cols < 4 && Math.ceil(rest.length / rows) > cols && (box.clientWidth + 26) / (cols + 1) >= 230) cols++;
    const visible = rows * cols;
    grid.style.gridTemplateRows = `repeat(${rows}, auto)`;
    grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    if (rest.length > visible) {
      [...grid.querySelectorAll(".shopitem")].slice(visible).forEach((el) => el.remove());
      note.textContent = `${total} items · ${visible + pinned.length} shown`;
      note.classList.add("warn");
    } else note.classList.remove("warn");
  }
  if (pin) pin.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
}
function currentScale() {
  const m = /scale\(([\d.]+)\)/.exec($("screen").style.transform || "");
  return m ? parseFloat(m[1]) || 1 : 1;
}

/* ─────────────────────────────── pie ─────────────────────────────── */
function renderFooter() {
  $("place").textContent = DATA.locationLabel || "Houston, TX";
  $("botCode").textContent = `REF ${String(DATA.version || "").slice(0, 8)}`;
  const names = { weather: "WX", calendar: "CAL", todoist: "LIST", nest: "NEST", alerts: "NWS", route: "ROUTE", radar: "RADAR" };
  const s = DATA.sources || {};
  $("sources").innerHTML = Object.keys(names).filter((k) => s[k]).map((k) => {
    const x = s[k];
    const cls = !x.ok ? "bad" : x.stale ? "stale" : "";
    return `<div class="src ${cls}" title="${escapeHtml(x.error || "")}"><b>${names[k]}</b><span>${!x.ok ? "OFFLINE" : x.stale ? "STALE" : "OK"}</span></div>`;
  }).join("");
}

function render() {
  if (!DATA) return;
  renderClock();
  renderNow();
  renderForecast();
  renderSide();
  renderWeek();
  renderSlot(true);
  renderRadar();
  renderNest();
  renderShop();
  renderFooter();
}

/* ─────────────────────────────── datos ─────────────────────────────── */
let failures = 0;
async function load() {
  try {
    const res = await fetch(API, { cache: "no-store" });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (VERSION && data.version && data.version !== VERSION) { location.reload(); return; }
    VERSION = data.version || VERSION;
    DATA = data;
    TZ = data.timezone || TZ;
    failures = 0;
    applyTheme();
    render();
  } catch (err) {
    failures++;
    toast(`Connection problem (${failures}): ${err.message}`);
  }
}

let toastTimer = null;
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 6000);
}

setInterval(() => { renderClock(); if (DATA) renderSlot(); }, 1000);
setInterval(applyTheme, 30000);
setInterval(load, 60000);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (DATA) render(); });

fit();
renderClock();
load();
window.monitorDebug = { get data() { return DATA; }, set data(d) { DATA = d; }, render };
