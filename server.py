#!/usr/bin/env python3
"""Monitor — servidor del tablero (solo stdlib, sin dependencias).

Sirve la pagina 1920x1080 y un endpoint /api/data que junta, con cache por
fuente y en paralelo:

  * clima actual + pronostico + salida/puesta del sol  (Open-Meteo, sin API key)
  * calendario de la semana                            (Google Calendar API)
  * Lista del Super del proyecto de Todoist            (Todoist API v1)
  * termostato Nest                                    (Google SDM, si esta configurado)

Cada fuente falla sola: si una se cae, /api/data devuelve su error y el resto
del tablero sigue funcionando (la pagina muestra el hueco, no datos inventados).

Uso:
  python3 server.py                 # http://0.0.0.0:8770
  python3 server.py --port 8080 --mock
  python3 server.py --once          # imprime el JSON una vez y sale
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
WEB = BASE / "web"
sys.path.insert(0, str(BASE))
import ics_lib  # noqa: E402  libreria de ICS/repeticiones (solo stdlib)

CONFIG_PATH = BASE / "config.json"

# ----------------------------------------------------------------- utilidades


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def read_text(path: str) -> str | None:
    try:
        return Path(os.path.expanduser(path)).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def http_json(url: str, *, method: str | None = None, headers: dict | None = None,
              body: dict | None = None, form: dict | None = None,
              timeout: int = 20) -> dict:
    """JSON por HTTP. Sin method explicito: GET si no hay datos, POST si los hay
    (mandar un cuerpo con method='GET' hace que Google conteste con una pagina
    400 de HTML en vez de invalid_grant, y eso confunde el diagnostico)."""
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    if method is None:
        method = "POST" if data is not None else "GET"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"):
        os.environ.pop(var, None)  # un proxy mal puesto rompe iCloud/Google
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
    return json.loads(raw) if raw.strip() else {}


def short_error(text: str, limit: int = 180) -> str:
    """Errores que van al tablero: sin HTML, sin ruido, en una linea."""
    t = (text or "").replace("\n", " ")
    low = t.lower()
    if "invalid_grant" in low:
        return ("Google: la credencial vencio o la revocaron — hay que autorizar "
                "otra vez (invalid_grant)")
    if "insufficient" in low or "insufficientpermissions" in low:
        return "Google: la credencial no tiene permiso para leer el calendario"
    if "<!doctype" in low or "<html" in low:
        return "el servicio respondio con una pagina de error en vez de datos"
    return t[:limit] + ("…" if len(t) > limit else "")


def fetch_ics(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


class Cache:
    """Cache por fuente con TTL y 'ultimo bueno' para servir algo si truena."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[float, object]] = {}
        self._last: dict[str, tuple[float, object]] = {}

    def run(self, key: str, ttl: int, fn):
        now = time.time()
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > now:
                value = hit[1]
                return (value, {"stale": False}) if isinstance(value, dict) or True else value
        try:
            value = fn()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                prev = self._last.get(key)
            if prev:
                return prev[1], {"stale": True, "error": f"{exc}"}
            return None, {"stale": False, "error": f"{exc}"}
        with self._lock:
            self._data[key] = (now + ttl, value)
            self._last[key] = (now, value)
        return value, {"stale": False, "error": None}


CACHE = Cache()

# --------------------------------------------------------------------- clima

WMO = {
    0: ("Clear sky", "clear"),
    1: ("Mainly clear", "mostly-clear"),
    2: ("Partly cloudy", "partly-cloudy"),
    3: ("Overcast", "cloudy"),
    45: ("Fog", "fog"),
    48: ("Rime fog", "fog"),
    51: ("Light drizzle", "drizzle"),
    53: ("Drizzle", "drizzle"),
    55: ("Heavy drizzle", "drizzle"),
    56: ("Freezing drizzle", "sleet"),
    57: ("Freezing drizzle", "sleet"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "sleet"),
    67: ("Freezing rain", "sleet"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Light showers", "showers"),
    81: ("Showers", "showers"),
    82: ("Violent showers", "showers"),
    85: ("Snow showers", "snow"),
    86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "thunder"),
    96: ("Thunderstorm, hail", "thunder"),
    99: ("Thunderstorm, hail", "thunder"),
}


def wmo(code) -> tuple[str, str]:
    return WMO.get(int(code or 0), ("Unknown", "cloudy"))


def weather(cfg: dict, mock: bool) -> dict:
    loc = cfg["location"]
    tz = ZoneInfo(loc["timezone"])
    if mock:
        now = datetime.now(tz)
        base = [1, 2, 3, 61, 80, 2]
        days = []
        for i in range(7):
            d = now.date() + timedelta(days=i)
            desc, icon = wmo(base[i % len(base)])
            days.append({
                "date": d.isoformat(), "code": base[i % len(base)], "desc": desc,
                "icon": icon, "maxC": 28 + (i % 3), "minC": 16 + (i % 4),
                "rainPct": (i * 13) % 60, "sunrise": f"{d.isoformat()}T07:2{8}",
                "sunset": f"{d.isoformat()}T18:4{5 - i % 5}",
            })
        return {
            "unit": "C",
            "current": {"tempC": 27.3, "feelsC": 28.8, "humidity": 51,
                        "windKph": 7.7, "code": 1, "desc": "Mainly clear",
                        "icon": "mostly-clear", "isDay": True},
            "daily": days,
            "sun": {"sunrise": days[0]["sunrise"], "sunset": days[0]["sunset"]},
            "placeholder": True,
        }

    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": loc["lat"], "longitude": loc["lon"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "weather_code,wind_speed_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,sunrise,sunset",
        "timezone": loc["timezone"], "forecast_days": 7,
        "temperature_unit": "celsius", "wind_speed_unit": "kmh",
    })
    raw = http_json(url, timeout=20)
    cur = raw.get("current", {})
    desc, icon = wmo(cur.get("weather_code"))
    daily = []
    d = raw.get("daily", {})
    for i, day in enumerate(d.get("time", [])):
        ddesc, dicons = wmo(d["weather_code"][i])
        daily.append({
            "date": day, "code": d["weather_code"][i], "desc": ddesc, "icon": dicons,
            "maxC": round(d["temperature_2m_max"][i], 1),
            "minC": round(d["temperature_2m_min"][i], 1),
            "rainPct": d.get("precipitation_probability_max", [None] * 7)[i],
            "sunrise": d["sunrise"][i], "sunset": d["sunset"][i],
        })
    return {
        "unit": "C",
        "current": {
            "tempC": round(cur.get("temperature_2m", 0), 1),
            "feelsC": round(cur.get("apparent_temperature", 0), 1),
            "humidity": cur.get("relative_humidity_2m"),
            "windKph": cur.get("wind_speed_10m"),
            "code": cur.get("weather_code"), "desc": desc, "icon": icon,
            "isDay": bool(cur.get("is_day", 1)),
        },
        "daily": daily,
        "sun": {"sunrise": daily[0]["sunrise"] if daily else None,
                "sunset": daily[0]["sunset"] if daily else None},
    }


# --------------------------------------------------------------- calendario


def load_calendars(cfg: dict) -> list[dict]:
    """Los calendarios salen de calendars.json (0600): nombre, cuenta, color y
    la direccion secreta en formato iCal de cada uno."""
    path = Path(os.path.expanduser(cfg["calendar"]["configFile"]))
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [c for c in data.get("calendars", []) if c.get("enabled", True)]


def ui_event(ev: dict) -> dict:
    """Del evento de ics_lib al que pinta la pagina."""
    return {
        "id": ev.get("occurrenceKey") or ev.get("uid"),
        "calendar": ev.get("calendar") or "",
        "title": ev.get("summary") or "(no title)",
        "location": ev.get("location") or None,
        "start": ev.get("start") or f"{ev.get('startDay', '')}T00:00",
        "end": ev.get("end") or None,
        "allDay": bool(ev.get("allDay")),
        "color": ev.get("color") or "#4f7cf7",
    }


def calendar_week(cfg: dict, mock: bool) -> dict:
    """La semana del tablero, leida de las direcciones iCal secretas.

    Solo lectura: el tablero nunca da de alta ni modifica eventos. Un calendario
    que falle no tumba la semana; se reporta en `errors` y los demas siguen.
    """
    tz = ZoneInfo(cfg["location"]["timezone"])
    today = datetime.now(tz).date()
    days = cfg["week"]["days"]
    start = today + timedelta(days=cfg["week"].get("startOffset", 0))
    end = start + timedelta(days=days - 1)

    if mock:
        palette = {"Home": "#e5a50a", "Work": "#e5484d", "Family": "#1a7a45",
                   "Personal": "#7c5cd6", "Holidays": "#0d9aa8",
                   "Moon phases": "#8a94a6", "Work (2nd account)": "#26418e"}
        samples = [
            (0, [("15:40", "Dentist", "Home", "123 Main St"),
                 ("09:00", "Team standup", "Work", None)]),
            (1, [("12:30", "Lunch with Sam", "Family", None),
                 ("20:00", "Take out the trash", "Home", None)]),
            (2, [("12:00", "Lunch", "Work", None)]),
            (3, [("all", "Full Moon", "Moon phases", None)]),
            (4, [("17:30", "Dinner reservation", "Family", "456 Oak Ave")]),
            (5, []),
            (6, [("07:30", "Pick up groceries", "Work", None),
                 ("all", "Sample holiday", "Holidays", None)]),
        ]
        out_days = []
        for off in range(days):
            d = start + timedelta(days=off)
            evs = []
            for t, title, cal, loc in (samples[off][1] if off < len(samples) else []):
                allday = t == "all"
                st = (datetime.combine(d, datetime.min.time(), tz).isoformat()
                      if allday else
                      datetime.strptime(f"{d.isoformat()} {t}", "%Y-%m-%d %H:%M")
                      .replace(tzinfo=tz).isoformat())
                en = (datetime.combine(d + timedelta(days=1), datetime.min.time(), tz).isoformat()
                      if allday else None)
                evs.append({"id": f"mock-{off}-{title}", "calendar": cal,
                            "title": title, "location": loc, "start": st, "end": en,
                            "allDay": allday, "color": palette.get(cal, "#5b8def")})
            evs.sort(key=lambda e: (not e["allDay"], e["start"] or ""))
            out_days.append({"date": d.isoformat(), "events": evs})
        return {"ok": True, "placeholder": True,
                "calendars": [{"name": k, "color": v} for k, v in palette.items()],
                "days": out_days, "range": {"start": start.isoformat(), "end": end.isoformat()}}

    feeds = load_calendars(cfg)
    if not feeds:
        # sin calendarios no es un error del tablero: está sin configurar
        return {"calendars": [], "unconfigured": True,
                "days": [{"date": (start + timedelta(days=off)).isoformat(), "events": []}
                         for off in range(days)],
                "range": {"start": start.isoformat(), "end": end.isoformat()},
                "errors": [], "foundCount": 0, "eventsInWindow": 0}

    def pull(feed: dict) -> list[dict]:
        text = ics_lib.fetch_ics(feed["url"], timeout=30)
        return ics_lib.parse_feed(
            text, feed.get("account", ""), "", feed["name"],
            feed.get("color") or "#4f7cf7", tz, start, end)

    errors: list[dict] = []
    events: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(6, len(feeds))) as pool:
        futures = {feed["name"]: pool.submit(pull, feed) for feed in feeds}
        for name, fut in futures.items():
            try:
                events.extend(fut.result())
            except Exception as exc:  # noqa: BLE001
                errors.append({"calendar": name, "error": short_error(str(exc))})

    if not events and errors and len(errors) == len(feeds):
        raise RuntimeError("; ".join(f"{e['calendar']}: {e['error']}" for e in errors))

    seen: set[str] = set()
    unique = []
    for ev in events:
        key = ev.get("occurrenceKey") or f"{ev.get('uid')}|{ev.get('startDay')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(ev)

    out_days = []
    for off in range(days):
        iso = (start + timedelta(days=off)).isoformat()
        picked = []
        for ev in unique:
            if ev.get("declined"):
                continue
            if ev["allDay"]:
                if ev["startDay"] <= iso <= ev["endDay"]:
                    picked.append(ev)
            elif ev["startDay"] == iso:
                picked.append(ev)
        picked.sort(key=lambda e: (not e["allDay"], e.get("start") or "", e["summary"]))
        out_days.append({"date": iso, "events": [ui_event(e) for e in picked]})

    return {
        "calendars": [{"name": f["name"], "color": f.get("color") or "#4f7cf7",
                       "account": f.get("account", "")} for f in feeds],
        "days": out_days,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "errors": errors,
        "foundCount": len(feeds),
        "eventsInWindow": len(unique),
    }


# ------------------------------------------------------------------ Todoist


def todoist_list(cfg: dict, mock: bool) -> dict:
    t = cfg["todoist"]
    project = t["project"]
    if mock:
        return {"project": "Shopping List", "placeholder": True,
                "items": [{"id": "1", "content": "Milk", "pinned": True},
                          {"id": "2", "content": "Eggs", "pinned": True},
                          {"id": "3", "content": "Coffee", "pinned": False},
                          {"id": "4", "content": "Bananas", "pinned": False},
                          {"id": "5", "content": "Bread", "pinned": False},
                          {"id": "6", "content": "Tortillas", "pinned": False}],
                "count": 6, "pinnedCount": 2}

    raw = os.environ.get("TODOIST_API_TOKEN") or read_text(t["tokenFile"]) or ""
    token = ""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if "api_token" in line:
            token = line.split("=", 1)[1].strip() if "=" in line else line
            break
    if not token:
        token = raw.strip().splitlines()[0].strip()
    if not token:
        raise RuntimeError(f"falta el token de Todoist ({t['tokenFile']})")
    headers = {"Authorization": f"Bearer {token}"}

    def paged(path: str, params: dict | None = None) -> list[dict]:
        out, cursor = [], None
        while True:
            p = dict(params or {})
            p["limit"] = 200
            if cursor:
                p["cursor"] = cursor
            r = http_json("https://api.todoist.com/api/v1" + path + "?" +
                          urllib.parse.urlencode(p), headers=headers, timeout=20)
            if isinstance(r, list):
                out.extend(r)
                return out
            out.extend(r.get("results", []))
            cursor = r.get("next_cursor")
            if not cursor:
                return out

    projects = paged("/projects")
    target = None
    norm = lambda s: "".join(ch for ch in (s or "").lower() if ch.isalnum())  # noqa: E731
    for p in projects:
        if norm(p["name"]) == norm(project):
            target = p
            break
    if target is None:
        partial = [p for p in projects if norm(project) in norm(p["name"])]
        if len(partial) == 1:
            target = partial[0]
    if target is None:
        raise RuntimeError(f"no encontre el proyecto '{project}' en Todoist")

    tasks = paged("/tasks", {"project_id": target["id"]})
    pinned = int(t.get("pinnedCount", 0))
    items = []
    for i, task in enumerate(tasks):
        items.append({"id": task["id"], "content": task.get("content", ""),
                      "pinned": i < pinned,
                      "priority": task.get("priority", 1)})
    return {"project": target["name"], "items": items, "count": len(items),
            "pinnedCount": pinned}


# ------------------------------------------------------------------- alertas


SEVERITY_ORDER = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}


def weather_alerts(cfg: dict, mock: bool) -> dict:
    """Avisos oficiales del NWS (api.weather.gov) para el punto de la casa."""
    a = cfg.get("alerts") or {}
    if mock:
        return {"count": 1, "source": "demo",
                "items": [{"event": "Air Quality Alert", "severity": "Moderate",
                           "headline": "Air Quality Alert issued October 21 at 3:49PM CDT "
                                       "by NWS Houston/Galveston TX",
                           "area": "Inland Harris", "ends": None}]}
    if not a.get("enabled", True):
        raise RuntimeError("alertas apagadas en config.json")

    lat = a.get("lat") or cfg["location"]["lat"]
    lon = a.get("lon") or cfg["location"]["lon"]
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
    raw = http_json(url, headers={
        "User-Agent": a.get("userAgent", "monitor-dashboard/1.0 (wall display)"),
        "Accept": "application/geo+json",
    }, timeout=25)

    items = []
    for feature in raw.get("features", []):
        p = feature.get("properties") or {}
        if (p.get("status") or "").lower() == "test":
            continue
        items.append({
            "event": p.get("event") or "Weather alert",
            "severity": p.get("severity") or "Unknown",
            "headline": (p.get("headline") or "").strip(),
            "area": (p.get("areaDesc") or "").split(";")[0].strip(),
            "ends": p.get("ends") or p.get("expires"),
            "onset": p.get("onset") or p.get("effective"),
        })
    items.sort(key=lambda i: SEVERITY_ORDER.get(i["severity"], 9))
    return {"count": len(items), "items": items[:4], "source": "api.weather.gov"}


# --------------------------------------------------------------------- ruta


def route_info(cfg: dict, mock: bool) -> dict:
    """Ruta en coche casa -> escuela (OSRM, línea base sin tráfico)."""
    r = cfg.get("route") or {}
    dest = (r.get("to") or {}).get("label") or "School"
    if mock:
        return {"km": 11.2, "min": 13, "destination": dest, "profile": "driving",
                "source": "demo"}
    if not r.get("enabled", True):
        raise RuntimeError("ruta apagada en config.json")

    o, d = r.get("from") or {}, r.get("to") or {}
    if not all(k in o for k in ("lat", "lon")) or not all(k in d for k in ("lat", "lon")):
        raise RuntimeError("faltan coordenadas de origen/destino en config.json (route)")
    profile = r.get("profile", "driving")
    url = (f"https://router.project-osrm.org/route/v1/{profile}/"
           f"{o['lon']},{o['lat']};{d['lon']},{d['lat']}?overview=false")
    raw = http_json(url, timeout=20)
    route = (raw.get("routes") or [None])[0]
    if not route:
        raise RuntimeError("OSRM no devolvió ninguna ruta")
    return {"km": round(route["distance"] / 1000, 1),
            "min": round(route["duration"] / 60),
            "destination": dest, "profile": profile, "source": "OSRM"}


def fresh_live_route(cfg: dict) -> dict | None:
    """El tráfico en vivo que deja traffic-live.py (TheGrid2), si no está viejo.

    Si el archivo no existe o ya pasó el límite de edad, se devuelve None y la
    tarjeta se queda con la línea base de OSRM: nunca se enseña un dato rancio
    como si fuera de ahora.
    """
    r = cfg.get("route") or {}
    path = Path(os.path.expanduser(r.get("liveFile") or "~/.hermes/traffic.json"))
    max_age = float(r.get("liveMaxAgeMinutes", 25))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        when = datetime.fromisoformat(str(data["measuredAt"]))
    except Exception:  # noqa: BLE001
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=ZoneInfo(cfg["location"]["timezone"]))
    age_min = (datetime.now(ZoneInfo(cfg["location"]["timezone"])) - when).total_seconds() / 60
    if age_min < 0 or age_min > max_age:
        return None
    return {"min": data.get("min"), "km": data.get("km"), "via": data.get("via") or "",
            "note": data.get("note") or "", "ageMin": round(age_min),
            "measuredAt": data.get("measuredAt")}


# --------------------------------------------------------------------- Nest


def nest_state(cfg: dict, mock: bool) -> dict:
    n = cfg.get("nest", {})
    if mock:
        return {"ambientC": 20.0, "targetC": 20.0, "humidity": 52,
                "mode": "HEATCOOL", "status": "OFF", "placeholder": True}
    if not n.get("enabled"):
        raise RuntimeError("Nest sin configurar")
    mode = n.get("mode", "sdm")
    if mode == "sdm":
        token_path = os.path.expanduser(n["refreshTokenFile"])
        cred = json.loads(Path(token_path).read_text(encoding="utf-8"))
        payload = http_json("https://oauth2.googleapis.com/token", form={
            "client_id": cred["client_id"], "client_secret": cred["client_secret"],
            "refresh_token": cred["refresh_token"], "grant_type": "refresh_token"})
        tok = payload["access_token"]
        dev = n["deviceId"]
        res = http_json(
            f"https://smartdevicemanagement.googleapis.com/v1/enterprises/"
            f"{n['projectId']}/devices/{dev}",
            headers={"Authorization": f"Bearer {tok}"})
        tr = res.get("traits", {})
        amb = tr.get("sdm.devices.traits.Temperature", {}).get("ambientTemperatureCelsius")
        hum = tr.get("sdm.devices.traits.Humidity", {}).get("ambientHumidityPercent")
        sp = tr.get("sdm.devices.traits.ThermostatTemperatureSetpoint", {})
        target = sp.get("heatCelsius", sp.get("coolCelsius"))
        return {"name": tr.get("sdm.devices.traits.Info", {}).get("customName", "Nest"),
                "ambientC": round(amb, 1) if amb is not None else None,
                "targetC": round(target, 1) if target is not None else None,
                "humidity": hum,
                "mode": tr.get("sdm.devices.traits.ThermostatMode", {}).get("mode"),
                "status": tr.get("sdm.devices.traits.ThermostatHvac", {}).get("status")}
    if mode == "http":
        return http_json(n["url"], headers={"Authorization": n.get("auth", "")})
    raise RuntimeError(f"modo de Nest desconocido: {mode}")


# ------------------------------------------------------------------ armado


def web_version() -> str:
    """Huella de web/ para que la pagina se recargue sola cuando hay cambios."""
    h = hashlib.sha1()
    for name in ("index.html", "style.css", "app.js"):
        path = WEB / name
        try:
            st = path.stat()
            h.update(f"{name}:{st.st_mtime_ns}:{st.st_size}".encode())
        except OSError:
            h.update(f"{name}:missing".encode())
    return h.hexdigest()[:12]


def build_payload(cfg: dict, mock: bool) -> dict:
    tz = ZoneInfo(cfg["location"]["timezone"])
    now = datetime.now(tz)
    jobs = {
        "weather": (600, lambda: weather(cfg, mock)),
        "calendar": (300, lambda: calendar_week(cfg, mock)),
        "todoist": (300, lambda: todoist_list(cfg, mock)),
        "nest": (120, lambda: nest_state(cfg, mock)),
        "alerts": (600, lambda: weather_alerts(cfg, mock)),
        "route": (300, lambda: route_info(cfg, mock)),
    }
    out: dict = {"generatedAt": now.isoformat(), "version": web_version(),
                 "timezone": cfg["location"]["timezone"],
                 "today": now.date().isoformat(), "now": now.isoformat(),
                 "locationLabel": cfg["location"].get("label", ""),
                 "config": {"week": cfg["week"], "theme": cfg.get("theme", {}),
                            "radar": cfg.get("radar", {}),
                            "slot": {
                                "routeWindows": (cfg.get("route") or {}).get("windows") or [],
                                "routeWeekdaysOnly": (cfg.get("route") or {}).get(
                                    "weekdaysOnly", True),
                                "rotateSeconds": (cfg.get("alerts") or {}).get(
                                    "rotateSeconds", 300),
                            }},
                 "sources": {}}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {name: pool.submit(CACHE.run, name, ttl, fn)
                   for name, (ttl, fn) in jobs.items()}
        for name, fut in futures.items():
            value, meta = fut.result()
            if value is None:
                out[name] = None
                out["sources"][name] = {"ok": False,
                                        "error": short_error(str(meta.get("error")))}
            else:
                out[name] = value
                out["sources"][name] = {"ok": True, "stale": bool(meta.get("stale")),
                                        "error": short_error(str(meta.get("error")))
                                        if meta.get("error") else None}
    # el tráfico en vivo (traffic-live.py en TheGrid2) se refresca fuera del cache
    if isinstance(out.get("route"), dict):
        live = fresh_live_route(cfg)
        if live:
            out["route"]["live"] = live
        else:
            out["route"].pop("live", None)
    return out


# ------------------------------------------------------------------- server


class Handler(SimpleHTTPRequestHandler):
    mock = False
    cfg: dict = {}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):  # silencio util
        if os.environ.get("MONITOR_DEBUG"):
            super().log_message(fmt, *args)

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] in ("/api/data", "/api/data/"):
            try:
                payload = build_payload(self.cfg, self.mock)
                body = json.dumps(payload).encode()
                self.send_response(200)
            except Exception as exc:  # noqa: BLE001
                body = json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode()
                self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def end_headers(self):
        if self.path.endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> int:
    ap = argparse.ArgumentParser(description="Monitor dashboard server")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--mock", action="store_true", help="datos de ejemplo (sin credenciales)")
    ap.add_argument("--once", action="store_true", help="imprime /api/data una vez y sale")
    args = ap.parse_args()

    cfg = load_config()
    mock = args.mock or os.environ.get("MONITOR_MOCK") == "1"
    if args.once:
        print(json.dumps(build_payload(cfg, mock), indent=2, ensure_ascii=False))
        return 0

    Handler.mock = mock
    Handler.cfg = cfg
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Monitor en http://{args.host}:{args.port}  (mock={mock})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
