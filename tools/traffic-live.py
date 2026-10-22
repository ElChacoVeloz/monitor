#!/usr/bin/env python3
"""Mide el tráfico en vivo casa -> escuela y se lo deja al tablero de la pared.

Cómo funciona: abre la ruta en Google Maps con Chromium headless, lee el primer
resultado (minutos, millas y la vía) y escribe un JSON que el Monitor lee. El
archivo se empuja a la Pi por SSH, así que la pantalla no depende de esta máquina
para dibujar: si el dato está viejo, el tablero cae solo a la línea base.

Se corre desde cron cada 10 minutos; **solo mide dentro de las ventanas** que
diga `~/monitor/config.json` (route.windows) y de lunes a viernes. Fuera de ahí
sale en silencio.

Uso:
  traffic-live.py                 # mide (si toca) y empuja a la Pi
  traffic-live.py --force         # mide aunque esté fuera de la ventana
  traffic-live.py --print         # mide y muestra, sin empujar
  traffic-live.py --push-only     # reenvía el último JSON sin medir
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CONFIG = Path(os.path.expanduser("~/monitor/config.json"))
OUT = Path(os.path.expanduser("~/.hermes/traffic.json"))
FAIL_STATE = Path(os.path.expanduser("~/.hermes/traffic-fail.state"))
FAIL_QUIET_MINUTES = 60          # no avisar más de una vez por hora si se rompe
PI_HOST = os.environ.get("MONITOR_HOST", "monitor")
PI_KEY = os.path.expanduser(
    os.environ.get("MONITOR_KEY", "~/.ssh/thegrid2_to_monitor_ed25519"))
CHROME = os.environ.get("CHROME_BIN", "chromium")
TZ = ZoneInfo("America/Chicago")
MILES_TO_KM = 1.609344


def log(msg: str) -> None:
    print(msg, flush=True)


def should_alert() -> bool:
    """¿Toca avisar de un fallo? Sí, pero máximo una vez por hora."""
    now = datetime.now(TZ).timestamp()
    try:
        last = float(FAIL_STATE.read_text(encoding="utf-8").strip())
        if now - last < FAIL_QUIET_MINUTES * 60:
            return False
    except Exception:  # noqa: BLE001
        pass
    try:
        FAIL_STATE.write_text(str(now), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return True


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def in_window(cfg: dict, now: datetime) -> dict | None:
    """¿Toca medir? Devuelve la ventana activa o None."""
    route = cfg.get("route") or {}
    if not route.get("enabled", True):
        return None
    if route.get("weekdaysOnly", True) and now.weekday() > 4:
        return None
    hhmm = now.strftime("%H:%M")
    for window in route.get("windows") or []:
        if window.get("start", "00:00") <= hhmm < window.get("end", "24:00"):
            return window
    return None


def maps_url(cfg: dict) -> str:
    route = cfg.get("route") or {}
    o, d = route.get("from") or {}, route.get("to") or {}
    return ("https://www.google.com/maps/dir/?api=1"
            f"&origin={o.get('lat')},{o.get('lon')}"
            f"&destination={d.get('lat')},{d.get('lon')}&travelmode=driving")


def dump_page(url: str, timeout: int = 90) -> str:
    """Abre la ruta con Chromium headless y devuelve el DOM."""
    profile = tempfile.mkdtemp(prefix="gm-")
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
           f"--user-data-dir={profile}", "--hide-scrollbars",
           "--window-size=1400,900", "--virtual-time-budget=20000",
           "--dump-dom", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout or ""


def text_of(dom: str) -> str:
    """DOM -> texto plano (fuera scripts, estilos y etiquetas)."""
    txt = re.sub(r"<script.*?</script>", " ", dom, flags=re.S)
    txt = re.sub(r"<style.*?</style>", " ", txt, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt)


# "17 min 7.4 miles via Memorial Dr and Hwy 6 S Best route now due to traffic..."
RE_ROUTE = re.compile(
    r"(\d{1,2})\s*min\s+([\d.]+)\s*mi(?:les)?"
    r"(?:\s+via\s+([A-Za-z0-9 .&#;'\-]{3,60}?)"
    r"(?=\s+(?:Best route|Fastest route|Details|View|Toll|\d{1,2}\s*min|$)))?")
RE_NOTE = re.compile(r"((?:Best|Fastest) route[^.]{0,60})")


def parse(dom: str) -> dict:
    txt = text_of(dom)
    match = RE_ROUTE.search(txt)
    if not match:
        raise RuntimeError("no encontré 'N min M miles' en la página de Google Maps")
    minutes = int(match.group(1))
    miles = float(match.group(2))
    via = (match.group(3) or "").strip(" ,·")
    if not (5 <= minutes <= 120 and 4 <= miles <= 40):
        raise RuntimeError(f"lectura fuera de rango: {minutes} min / {miles} mi")
    note_match = RE_NOTE.search(txt)
    note = note_match.group(1).strip() if note_match else ""
    for marker in ("Best route", "Fastest route"):   # el texto se repite en el DOM
        if note.count(marker) > 1:
            note = note[: note.find(marker, 1)].strip()
    return {
        "min": minutes,
        "km": round(miles * MILES_TO_KM, 1),
        "mi": miles,
        "via": via[:60],
        "note": note[:90],
        "source": "Google Maps (live)",
    }


def measure(cfg: dict) -> dict:
    dom = dump_page(maps_url(cfg))
    if "Google Maps" not in dom:
        raise RuntimeError("la página no cargó (¿sin red o cambio el HTML?)")
    data = parse(dom)
    now = datetime.now(TZ)
    data["measuredAt"] = now.isoformat(timespec="seconds")
    data["window"] = (in_window(cfg, now) or {}).get("label", "")
    return data


def push() -> bool:
    """Deja el JSON en la Pi (600). Devuelve True si llegó."""
    if not OUT.exists():
        log("no hay nada que empujar todavía")
        return False
    cmd = ["scp", "-q", "-i", PI_KEY, "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new",
           str(OUT), f"pi@{PI_HOST}:.hermes/traffic.json"]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        log(f"no pude empujar a la Pi: {done.stderr.strip()[:160]}")
        return False
    subprocess.run(["ssh", "-i", PI_KEY, "-o", "BatchMode=yes",
                    "-o", "StrictHostKeyChecking=accept-new", f"pi@{PI_HOST}",
                    "chmod 600 ~/.hermes/traffic.json"], capture_output=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Tráfico en vivo para el Monitor")
    ap.add_argument("--force", action="store_true", help="medir aunque no toque")
    ap.add_argument("--print", dest="show", action="store_true",
                    help="solo mostrar, sin escribir ni empujar")
    ap.add_argument("--push-only", action="store_true",
                    help="reenviar el último JSON a la Pi")
    args = ap.parse_args()

    cfg = load_config()
    now = datetime.now(TZ)

    if args.push_only:
        return 0 if push() else 1
    if not args.force and not args.show and not in_window(cfg, now):
        return 0                      # fuera de ventana: silencio

    try:
        data = measure(cfg)
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {str(exc)[:120]}"
        if should_alert():                      # avisa por Telegram, pero sin spam
            log(f"tráfico en vivo: fallo al medir ({detail}) — el tablero "
                f"se queda con la línea base de OSRM")
            return 1
        return 0

    if args.show:
        log(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    FAIL_STATE.unlink(missing_ok=True)          # se curó: la próxima falla sí avisa
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(OUT, 0o600)
    if not push():
        return 1
    log(f"tráfico en vivo: {data['min']} min / {data['km']} km "
        f"({data['via'] or 'sin vía'}) → empujado a la Pi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
