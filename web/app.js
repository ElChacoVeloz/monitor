/* Monitor — front end. Sin dependencias: lee /api/data y dibuja el tablero. */

const $ = (id) => document.getElementById(id);
const API = "/api/data";

/* ───────────────────────── iconos de clima (WMO) ───────────────────────── */
const C = { sun: "#f5a623", cloud: "#9db3cc", cloud2: "#c3d2e3", rain: "#4a9df0",
            snow: "#a9cbef", bolt: "#f5c542", fog: "#b3c0d1", moon: "#7f9bdd" };

const CLOUD = `<path d="M19 44h27a9.6 9.6 0 0 0-1.9-19A13.6 13.6 0 0 0 19.4 27 8.6 8.6 0 0 0 19 44z" fill="${C.cloud}"/>`;
const CLOUD2 = `<path d="M15 34h23a8.2 8.2 0 0 0-1.6-16.2A11.6 11.6 0 0 0 15.4 18.5 7.3 7.3 0 0 0 15 34z" fill="${C.cloud2}"/>`;
const SUNBIG = (cx, cy, r) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${C.sun}"/>
  <g stroke="${C.sun}" stroke-width="3.4" stroke-linecap="round">
    <line x1="${cx}" y1="${cy - r - 9}" x2="${cx}" y2="${cy - r - 4}"/>
    <line x1="${cx}" y1="${cy + r + 4}" x2="${cx}" y2="${cy + r + 9}"/>
    <line x1="${cx - r - 9}" y1="${cy}" x2="${cx - r - 4}" y2="${cy}"/>
    <line x1="${cx + r + 4}" y1="${cy}" x2="${cx + r + 9}" y2="${cy}"/>
    <line x1="${cx - r - 6}" y1="${cy - r - 6}" x2="${cx - r - 3}" y2="${cy - r - 3}"/>
    <line x1="${cx + r + 3}" y1="${cy + r + 3}" x2="${cx + r + 6}" y2="${cy + r + 6}"/>
    <line x1="${cx + r + 6}" y1="${cy - r - 6}" x2="${cx + r + 3}" y2="${cy - r - 3}"/>
    <line x1="${cx - r - 3}" y1="${cy + r + 3}" x2="${cx - r - 6}" y2="${cy + r + 6}"/>
  </g>`;
const MOON = `<path d="M40 12a22 22 0 1 0 12 34A18 18 0 0 1 40 12z" fill="${C.moon}"/>`;
const DROPS = (n, y) => Array.from({ length: n }, (_, i) =>
  `<path d="M${19 + i * 9} ${y}c0 0-3.2 3.6-3.2 5.6a3.2 3.2 0 0 0 6.4 0c0-2-3.2-5.6-3.2-5.6z" fill="${C.rain}"/>`).join("");
const FLAKES = (y) => [0, 1, 2].map((i) => {
  const x = 21 + i * 11;
  return `<g stroke="${C.snow}" stroke-width="2.4" stroke-linecap="round">
    <line x1="${x - 3.4}" y1="${y}" x2="${x + 3.4}" y2="${y}"/>
    <line x1="${x - 1.7}" y1="${y - 3}" x2="${x + 1.7}" y2="${y + 3}"/>
    <line x1="${x - 1.7}" y1="${y + 3}" x2="${x + 1.7}" y2="${y - 3}"/></g>`; }).join("");
const BOLT = `<path d="M33 38l-9 15h8l-3 11 13-17h-8l4-9z" fill="${C.bolt}"/>`;

const ICONS = {
  "clear-day": SUNBIG(32, 32, 13),
  "clear-night": MOON,
  "mostly-clear": SUNBIG(24, 22, 9) + CLOUD,
  "partly-cloudy": SUNBIG(23, 20, 10) + CLOUD,
  "cloudy": CLOUD2 + CLOUD,
  "fog": CLOUD + `<g stroke="${C.fog}" stroke-width="3.2" stroke-linecap="round">
      <line x1="16" y1="50" x2="46" y2="50"/><line x1="21" y1="56" x2="41" y2="56"/></g>`,
  "drizzle": CLOUD + DROPS(2, 48),
  "rain": CLOUD + DROPS(3, 48),
  "showers": SUNBIG(23, 20, 9) + CLOUD + DROPS(2, 48),
  "sleet": CLOUD + DROPS(2, 48) + FLAKES(58),
  "snow": CLOUD + FLAKES(53),
  "thunder": CLOUD + BOLT,
};
const iconSvg = (kind, isDay) => {
  let k = kind;
  if (k === "clear" ) k = isDay ? "clear-day" : "clear-night";
  if (k === "mostly-clear" && !isDay) k = "clear-night";
  if (k === "partly-cloudy" && !isDay) k = "cloudy";
  return `<svg viewBox="0 0 64 64" aria-hidden="true">${ICONS[k] || ICONS.cloudy}</svg>`;
};

/* iconos de interfaz */
const ICO = {
  sunrise: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
    stroke-linecap="round"><path d="M12 3v6M5 12H3m18 0h-2M7.5 7.5 6 6m12 1.5L19.5 6"/>
    <path d="M8 15a4 4 0 0 1 8 0"/><path d="M3 19h18"/></svg>`,
  sunset: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
    stroke-linecap="round"><path d="M12 9V3M5 12H3m18 0h-2M7.5 7.5 6 6m12 1.5L19.5 6"/>
    <path d="M8 15a4 4 0 0 1 8 0"/><path d="M3 19h18"/></svg>`,
  drop: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3s6 6.6 6 10.4A6 6 0 0 1 6 13.4C6 9.6 12 3 12 3z"/></svg>`,
  thermo: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
    stroke-linecap="round"><path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0z"/></svg>`,
  plug: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
    stroke-linecap="round"><path d="M9 3v6M15 3v6M6 9h12v3a6 6 0 0 1-12 0z"/><path d="M12 18v3"/></svg>`,
};

/* ─────────────────────────────── estado ─────────────────────────────── */
let DATA = null;
let TZ = "America/Chicago";
let VERSION = null;   // huella del front que tengo cargado

const fmtCache = new Map();
function fmt(opts) {
  /* la llave es el propio juego de opciones: dos llamadas con distinto formato
     no pueden compartir formateador (eso pintaba "Friday, October 23, 2026"
     donde iba solo "Friday") */
  const key = JSON.stringify(opts);
  if (!fmtCache.has(key)) {
    fmtCache.set(key, new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts }));
  }
  return fmtCache.get(key);
}

const px = (s) => parseFloat(s) || 0;

/* escala 1920x1080 a cualquier pantalla */
function fit() {
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  $("screen").style.transform = `scale(${s})`;
}
window.addEventListener("resize", fit);

/* ─────────────────────────── tema dia / noche ─────────────────────────── */
function applyTheme() {
  const sun = DATA && DATA.weather && DATA.weather.sun;
  const now = new Date();
  let rise = null, set = null;
  if (sun && sun.sunrise && sun.sunset) {
    rise = new Date(sun.sunrise);
    set = new Date(sun.sunset);
  }
  if (!rise || isNaN(rise) || !set || isNaN(set)) {
    rise = new Date(now); rise.setHours(7, 0, 0, 0);
    set = new Date(now); set.setHours(19, 0, 0, 0);
  }
  let isDay = now >= rise && now < set;
  /* ?theme=day|night fuerza la paleta (pruebas y kioscos fijos) */
  const forced = (new URLSearchParams(location.search).get("theme") || "").toLowerCase();
  if (forced === "day") isDay = true;
  if (forced === "night") isDay = false;
  const target = isDay ? "day" : "night";
  const root = document.documentElement;
  root.classList.remove("booting");
  if (!root.classList.contains(target)) {
    root.classList.remove("day", "night");
    root.classList.add(target);
    root.dataset.themeChanged = new Date().toISOString();
    if (DATA) render();            // los colores se adaptan al tema
  }
  try { localStorage.setItem("monitor.theme", target); } catch (e) {}
  return { isDay, rise, set };
}

/* ─────────────────────────────── render ─────────────────────────────── */
function renderClock() {
  const now = new Date();
  const t = fmt({ hour: "numeric", minute: "2-digit", hour12: true }).format(now);
  const [time, ampm] = t.split(" ");
  $("clockTime").textContent = time;
  $("clockAmPm").textContent = ampm || "";
  $("dateLong").textContent = fmt({ weekday: "long", month: "long", day: "numeric",
    year: "numeric" }).format(now);
  $("place").textContent = (DATA && DATA.locationLabel) || "Houston, TX";
}

function offlineBox(text, reason) {
  return `<div class="offline"><div class="offinner">${ICO.plug}
    <div><div class="offtitle">${escapeHtml(text)}</div>
    ${reason ? `<div class="offreason">${escapeHtml(reason)}</div>` : ""}</div>
  </div></div>`;
}
const srcError = (name) => (DATA && DATA.sources && DATA.sources[name] && DATA.sources[name].error) || "";

function renderNow(src) {
  const w = DATA.weather;
  const card = $("nowCard");
  const stale = DATA.sources.weather && DATA.sources.weather.stale;
  card.querySelectorAll(".stale").forEach((n) => n.remove());
  if (!w) {
    $("nowIcon").innerHTML = "";
    $("nowTemp").textContent = "--";
    $("nowDesc").textContent = "Weather unavailable";
    $("nowFeels").textContent = srcError("weather");
    return;
  }
  const cur = w.current;
  $("nowIcon").innerHTML = iconSvg(cur.icon, cur.isDay);
  $("nowTemp").textContent = Math.round(cur.tempC);
  $("nowDesc").textContent = cur.desc;
  $("nowFeels").textContent = `Feels like ${Math.round(cur.feelsC)}°C`;
  let extra = $("nowExtra");
  if (!extra) {
    extra = document.createElement("div");
    extra.className = "nowextra";
    extra.id = "nowExtra";
    card.querySelector(".nowtext").appendChild(extra);
  }
  extra.textContent = `${cur.humidity}% humidity · wind ${Math.round(cur.windKph)} km/h`;
  if (stale) card.insertAdjacentHTML("beforeend", `<div class="stale">cached</div>`);
}

function renderForecast() {
  const box = $("forecast");
  const w = DATA.weather;
  if (!w || !w.daily || !w.daily.length) { box.innerHTML = ""; return; }
  const n = (DATA.config.week.forecastDays || 5);
  const startsToday = DATA.config.week.forecastStartsToday !== false;
  const list = w.daily.slice(startsToday ? 0 : 1, (startsToday ? 0 : 1) + n);
  box.innerHTML = list.map((d, i) => {
    const dt = new Date(`${d.date}T12:00:00`);
    const label = startsToday
      ? (i === 0 ? "Today" : i === 1 ? "Tomorrow" : fmt({ weekday: "short" }).format(dt))
      : (i === 0 ? "Tomorrow" : fmt({ weekday: "short" }).format(dt));
    const rain = d.rainPct;
    return `<div class="fday">
      <div class="flabel">${label}</div>
      <div class="ficon">${iconSvg(d.icon, true)}</div>
      <div class="ftemps"><span class="fhi">${Math.round(d.maxC)}°</span>
        <span class="flo">${Math.round(d.minC)}°</span></div>
      <div class="frain ${rain ? "" : "off"}">${ICO.drop}${rain == null ? "--" : rain + "%"}</div>
    </div>`;
  }).join("");
}

function eventTime(ev) {
  if (ev.allDay) return "All day";
  const d = new Date(ev.start);
  if (isNaN(d)) return "";
  return fmt({ hour: "numeric", minute: "2-digit", hour12: true }).format(d);
}

const isNight = () => document.documentElement.classList.contains("night");

/* En la paleta oscura los colores muy oscuros (verde oscuro, azul marino) se
   pierden contra el fondo: se aclaran un poco para que la barra y el tinte se
   lean. De día se usan tal cual. */
function adaptColor(hex) {
  const h = (hex || "#5b8def").replace("#", "");
  const s = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(s.slice(0, 6), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  if (!isNight()) return { c: `rgb(${r}, ${g}, ${b})`, rgb: [r, g, b] };
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  if (lum >= 0.42) return { c: `rgb(${r}, ${g}, ${b})`, rgb: [r, g, b] };
  const mix = (v) => Math.round(v + (255 - v) * 0.38);
  const rr = mix(r), gg = mix(g), bb = mix(b);
  return { c: `rgb(${rr}, ${gg}, ${bb})`, rgb: [rr, gg, bb] };
}

function hexToRgba(hex, alpha) {
  const h = (hex || "#5b8def").replace("#", "");
  const s = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(s.slice(0, 6), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function renderWeek() {
  const box = $("week");
  const cal = DATA.calendar;
  const note = $("weekNote");
  if (!cal || !cal.days) {
    box.innerHTML = "";
    note.textContent = "";
    box.insertAdjacentHTML("afterend", "");
    box.parentElement.querySelector(".offline")?.remove();
    box.innerHTML = offlineBox("Calendar is not available right now",
      srcError("calendar"));
    box.classList.add("weekoff");
    return;
  }
  box.classList.remove("weekoff");
  if (cal.unconfigured) {
    box.classList.add("weekoff");
    box.innerHTML = offlineBox("No calendars yet",
      "run calendar-config.py add-missing on the server");
    note.textContent = "";
    return;
  }
  const days = cal.days;
  box.innerHTML = days.map((day, i) => {
    const dt = new Date(`${day.date}T12:00:00`);
    const label = i === 0 ? "Today" : i === 1 ? "Tomorrow" : fmt({ weekday: "long" }).format(dt);
    const num = fmt({ day: "numeric" }).format(dt);
    const mon = fmt({ month: "short" }).format(dt);
    const evs = day.events || [];
    const tint = isNight() ? 0.26 : 0.18;
    const cards = evs.map((ev) => {
      const col = adaptColor(ev.color);
      const bg = `rgba(${col.rgb[0]}, ${col.rgb[1]}, ${col.rgb[2]}, ${tint})`;
      return `
      <div class="evt ${ev.allDay ? "allday" : ""}" style="--ev:${col.c};
           border-left-color:${col.c}; background:${bg}">
        <div class="etime">${eventTime(ev)}</div>
        <div class="etitle">${escapeHtml(ev.title)}</div>
        ${ev.location && !ev.allDay ? `<div class="eloc">${escapeHtml(ev.location)}</div>` : ""}
      </div>`; }).join("");
    return `<div class="daycol ${i === 0 ? "today" : ""}" data-day="${i}">
      <div class="dayhead">
        <div class="daynum">${num}</div>
        <div class="dayname">${label}</div>
        <div class="daysub">${mon}</div>
      </div>
      <div class="events" data-day="${i}">${cards || `<div class="empty">—</div>`}</div>
    </div>`;
  }).join("");

  /* aprieta las columnas que no caben */
  box.querySelectorAll(".events").forEach((col) => {
    const day = box.querySelector(`.daycol[data-day="${col.dataset.day}"]`);
    const n = col.querySelectorAll(".evt").length;
    if (n > 0 && n <= 3) day.classList.add("sparse");   // pocos eventos: mas grandes
    if (col.scrollHeight > col.clientHeight + 2) day.classList.add("dense");
    if (col.scrollHeight > col.clientHeight + 2) day.classList.add("denser");
    let hidden = 0;
    const cards = [...col.querySelectorAll(".evt")];
    while (col.scrollHeight > col.clientHeight + 2 && cards.length - hidden > 1) {
      cards[cards.length - 1 - hidden].style.display = "none";
      hidden++;
    }
    if (hidden) col.insertAdjacentHTML("beforeend", `<div class="more">+${hidden} more</div>`);
  });

  const bits = [];
  if (cal.placeholder) bits.push("demo data");
  if (cal.range) bits.push(`${cal.range.start} → ${cal.range.end}`);
  if (cal.errors && cal.errors.length) {
    const names = cal.errors.map((e) => e.calendar).join(", ");
    bits.push(`${cal.errors.length} calendar${cal.errors.length === 1 ? "" : "s"} failing: ${names}`);
  }
  note.textContent = bits.join("  ·  ");
  note.title = (cal.errors || []).map((e) => `${e.calendar}: ${e.error}`).join("\n");
}

function renderSun() {
  const w = DATA.weather;
  const card = $("sunCard");
  if (!w || !w.sun || !w.sun.sunrise) {
    card.innerHTML = offlineBox("Sun times unavailable");
    return;
  }
  const f = (iso) => {
    const d = new Date(iso);
    return isNaN(d) ? "--" : fmt({ hour: "numeric", minute: "2-digit", hour12: true }).format(d);
  };
  card.innerHTML = `
    <div class="sunrow">${ICO.sunrise.replace("currentColor", "var(--sun)")}
      <div class="stext"><span class="slabel">Sunrise</span>
      <span class="stime">${f(w.sun.sunrise)}</span></div></div>
    <div class="sunrow">${ICO.sunset.replace("currentColor", "var(--moon)")}
      <div class="stext"><span class="slabel">Sunset</span>
      <span class="stime">${f(w.sun.sunset)}</span></div></div>`;
}

function renderNest() {
  const card = $("nestCard");
  const n = DATA.nest;
  if (!n) {
    card.innerHTML = `<div class="nesthead"><span class="nestname">Thermostat</span></div>
      <div class="offline" style="height:auto;margin-top:16px;padding:0;font-size:19px">
        ${ICO.plug}<span>${escapeHtml(srcError("nest") || "Nest not connected yet")}</span></div>`;
    return;
  }
  const t = (v) => (v == null ? "--" : v);
  const MODES = { HEAT: "Heat", COOL: "Cool", HEATCOOL: "Auto", OFF: "Off" };
  const STATUS = { HEATING: "Heating", COOLING: "Cooling", OFF: "Idle", FAN: "Fan" };
  const mode = MODES[(n.mode || "").toUpperCase()] || n.mode;
  const status = STATUS[(n.status || "").toUpperCase()] || n.status;
  card.innerHTML = `
    <div class="nesthead">
      <span class="nestname">${escapeHtml(n.name || "Thermostat")}</span>
      <span class="nestmode">${[mode, status].filter(Boolean).join(" · ")}</span>
    </div>
    <div class="nestbig">${t(n.targetC)}<span class="deg">°C</span></div>
    <div class="nestmetrics">
      <div class="metric">${ICO.thermo}<div><span class="mlabel">Ambient</span>${t(n.ambientC)}°C</div></div>
      <div class="metric">${ICO.drop}<div><span class="mlabel">Humidity</span>${t(n.humidity)}%</div></div>
    </div>`;
}

function renderShop() {
  const box = $("shop");
  const note = $("shopNote");
  const s = DATA.todoist;
  if (!s || !s.items) {
    box.innerHTML = offlineBox("Shopping list unavailable", srcError("todoist"));
    note.textContent = "";
    return;
  }
  const pinned = s.items.filter((i) => i.pinned);
  const rest = s.items.filter((i) => !i.pinned);
  const total = s.items.length;
  note.textContent = `${total} item${total === 1 ? "" : "s"}`;
  const row = (i) => `<div class="shopitem ${i.pinned ? "pinned" : ""}">
      <span class="${i.pinned ? "dot" : "box"}"></span>
      <span class="txt">${escapeHtml(i.content)}</span></div>`;
  if (!s.items.length) { box.innerHTML = `<div class="shopempty">Nothing on the list.</div>`; return; }
  let html = "";
  if (pinned.length) html += `<div class="shoppinned">${pinned.map(row).join("")}</div>`;
  if (rest.length) html += `<div class="shopgrid">${rest.map(row).join("")}</div>`;
  box.innerHTML = html;

  /* cuantos items caben de verdad: se mide, no se adivina, y lo que no cabe
     se dice en el encabezado (nada de items recortados sin avisar) */
  const grid = box.querySelector(".shopgrid");
  if (grid) {
    const gap = 6;
    const probe = document.createElement("div");
    probe.className = "shopitem";
    probe.innerHTML = `<span class="box"></span><span class="txt">X</span>`;
    grid.appendChild(probe);
    const itemH = probe.offsetHeight || 28;
    probe.remove();
    const boxTop = box.getBoundingClientRect().top;
    const avail = box.clientHeight - (grid.getBoundingClientRect().top - boxTop);
    const rows = Math.max(1, Math.floor((avail + gap) / (itemH + gap)));
    let cols = Math.max(1, Math.min(4, Math.floor((box.clientWidth + 26) / (280 + 26))));
    /* si truncaria demasiado, se agrega una columna mientras siga habiendo ancho */
    while (cols < 4 && Math.ceil(rest.length / rows) > cols &&
           (box.clientWidth + 26) / (cols + 1) >= 250) cols++;
    const visible = rows * cols;
    grid.style.gridTemplateRows = `repeat(${rows}, auto)`;
    grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;   // mismas pistas que los fijados
    const pin = box.querySelector(".shoppinned");
    if (pin) pin.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;  // mismas columnas
    if (rest.length > visible) {
      [...grid.querySelectorAll(".shopitem")].slice(visible)
        .forEach((el) => el.remove());
      note.textContent = `${total} items · ${visible + pinned.length} shown`;
    }
  }
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function render() {
  if (!DATA) return;
  renderClock();
  renderNow();
  renderForecast();
  renderWeek();
  renderSun();
  renderNest();
  renderShop();
}

/* ─────────────────────────────── datos ─────────────────────────────── */
let failures = 0;
async function load() {
  try {
    const res = await fetch(API, { cache: "no-store" });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (VERSION && data.version && data.version !== VERSION) {
      /* cambiaron los archivos del tablero: recarga para tomar el código nuevo */
      location.reload();
      return;
    }
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

/* cada segundo el reloj; cada minuto revisar tema; cada 60 s datos frescos */
setInterval(renderClock, 1000);
setInterval(() => { applyTheme(); }, 30000);
setInterval(load, 60000);

fit();
load();
