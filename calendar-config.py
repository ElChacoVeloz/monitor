#!/usr/bin/env python3
"""Las direcciones iCal de los calendarios del tablero.

Cada calendario de Google tiene una "Dirección secreta en formato iCal"
(Configuración → tu calendario → Dirección secreta en formato iCal): termina en
`/private-XXXXXXXX/basic.ics` y quien la tenga puede leer el calendario. Por eso
viven en `calendars.json` (chmod 600) y no en `config.json`, y por eso `add`
la pide sin mostrarla en pantalla.

Uso:
  calendar-config.py add --name "Home" [--account correo] [--color "#4f7cf7"]
  calendar-config.py list
  calendar-config.py check
  calendar-config.py remove --name "Home"
  calendar-config.py import-omarchy ~/.config/omarchy/plugins/elchacoveloz.calendar/config.json
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
STORE = BASE / "calendars.json"
CONFIG = BASE / "config.json"

PALETTE = ["#4f7cf7", "#e0533d", "#2fa87a", "#c65cc9", "#e8a33d",
           "#3aa6c9", "#8a94a6", "#d4703a", "#7a5cf0", "#4aa88a"]

def default_account() -> str:
    """La cuenta que se propone al dar de alta (config.json → calendar.defaultAccount)."""
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        return (cfg.get("calendar") or {}).get("defaultAccount") or "me@example.com"
    except Exception:  # noqa: BLE001
        return "me@example.com"


# nombres que propone `add-missing`; la cuenta sale de config.json
REQUIRED_NAMES = [
    "Home",
    "Work",
    "Family",
    "Personal",
    "Phases of the Moon",
]


def load() -> dict:
    if not STORE.exists():
        return {"calendars": []}
    data = json.loads(STORE.read_text(encoding="utf-8"))
    data.setdefault("calendars", [])
    return data


def save(data: dict) -> None:
    STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(STORE, 0o600)


def next_color(data: dict) -> str:
    used = {c.get("color") for c in data["calendars"]}
    for color in PALETTE:
        if color not in used:
            return color
    return PALETTE[len(data["calendars"]) % len(PALETTE)]


def mask(url: str) -> str:
    """Muestra de dónde es la dirección sin enseñar el token privado."""
    if not url:
        return "(sin url)"
    if "/ical/" in url:                     # Google: …/ical/<cuenta>/private-XXXX/basic.ics
        head = url.split("/ical/")[0]
        tail = url.rsplit("/", 1)[-1]
        if "private-" in url:
            return f"{head}/…/private-••••••/{tail}"
        return f"{head}/…/{tail}"
    # iCloud (webcal://…/published/<token>/<archivo>) y cualquier otro: host + cola.
    # El token de un feed publicado es un secreto completo, así que solo se
    # muestra cuando la cola es un nombre de archivo (basic.ics) y no el token.
    scheme, _, rest = url.partition("://")
    host, _, path = rest.partition("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    if "." in tail and len(tail) < 40:
        return f"{scheme}://{host}/…/{tail}"
    return f"{scheme}://{host}/…"


def find(data: dict, name: str) -> dict | None:
    for cal in data["calendars"]:
        if cal["name"].lower() == name.lower():
            return cal
    return None


def cmd_add(args) -> int:
    data = load()
    if find(data, args.name):
        print(f"ya existe un calendario llamado '{args.name}': usa otro nombre o "
              f"borralo con: calendar-config.py remove --name '{args.name}'")
        return 2
    url = args.url
    if not url:
        url = getpass.getpass(f"Dirección iCal secreta de «{args.name}» (no se muestra): ").strip()
    if not url:
        print("cancelado: sin dirección no hay calendario")
        return 2
    for other in data["calendars"]:
        if other.get("url", "").strip() == url:
            print(f"esa dirección ya la tiene «{other['name']}»: dos calendarios con la "
                  f"misma dirección pintan los mismos eventos (y uno se queda vacío).")
            print("copia la dirección del calendario que de verdad quieres.")
            return 2
    if not url.startswith(("https://", "webcal://")):
        print("aviso: no empieza con https:// ni webcal://; la guardo igual")
    entry = {"name": args.name, "account": args.account or default_account(),
             "color": args.color or next_color(data), "url": url, "enabled": True}
    data["calendars"].append(entry)
    save(data)
    print(f"guardado «{entry['name']}» ({entry['account']}, {entry['color']}) en {STORE}")
    print(mask(url))
    return 0


def cmd_list(args) -> int:
    data = load()
    if not data["calendars"]:
        print("no hay calendarios todavía. Agrega con: calendar-config.py add --name \"Home\"")
        return 1
    print(f"{len(data['calendars'])} calendario(s) en {STORE}:\n")
    for cal in data["calendars"]:
        flag = "" if cal.get("enabled", True) else "  (apagado)"
        print(f"  {cal['color']}  {cal['name']:<28} {cal.get('account',''):<32}{flag}")
        print(f"              {mask(cal.get('url',''))}")
    return 0


def cmd_color(args) -> int:
    """Cambiar el color de un calendario (el .ics no trae color)."""
    data = load()
    cal = find(data, args.name)
    if not cal:
        print(f"no hay ningún calendario llamado '{args.name}'")
        return 1
    color = args.color
    if not color.startswith("#"):
        color = "#" + color
    if len(color) not in (4, 7):
        print(f"color inválido: {color} (usa #rrggbb)")
        return 2
    before = cal.get("color")
    cal["color"] = color
    save(data)
    print(f"«{cal['name']}»: {before} → {color}")
    print("el tablero lo toma en el siguiente refresco (o reinicia el servidor)")
    return 0


def cmd_remove(args) -> int:
    data = load()
    cal = find(data, args.name)
    if not cal:
        print(f"no hay ningún calendario llamado '{args.name}'")
        return 1
    data["calendars"] = [c for c in data["calendars"] if c is not cal]
    save(data)
    print(f"borrado «{cal['name']}» (la dirección secreta se fue con él)")
    return 0


def cmd_check(args) -> int:
    """Prueba cada dirección y cuenta los eventos de la semana que empieza hoy."""
    data = load()
    if not data["calendars"]:
        print("no hay calendarios que probar")
        return 1
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg["location"]["timezone"])
    today = datetime.now(tz).date()
    end = today + timedelta(days=6)
    sys.path.insert(0, str(BASE))
    import ics_lib  # noqa: E402  (la librería vive junto a este script)

    urls = {}
    for cal in data["calendars"]:
        urls.setdefault(cal.get("url", "").strip(), []).append(cal["name"])
    for url, names in urls.items():
        if len(names) > 1:
            print(f"  OJO   misma dirección en: {', '.join(names)} "
                  f"(van a pintar los mismos eventos)")

    failures = 0
    for cal in data["calendars"]:
        name = cal["name"]
        try:
            text = ics_lib.fetch_ics(cal["url"], timeout=25)
            events = ics_lib.parse_feed(text, cal.get("account", ""), "", name,
                                        cal.get("color", PALETTE[0]), tz, today, end)
            today_count = sum(1 for e in events if e["startDay"] == today.isoformat())
            print(f"  ok    {name:<28} {len(events):>3} eventos esta semana"
                  f"  ({today_count} hoy)")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FALLA {name:<28} {type(exc).__name__}: {str(exc)[:90]}")
    return 1 if failures else 0


PUBLIC_FEEDS = [
    ("Holidays in United States", None, "#4f7cf7",
     "https://calendar.google.com/calendar/ical/"
     "en.usa%23holiday%40group.v.calendar.google.com/public/basic.ics"),
    ("Holidays in Mexico", None, "#2fa87a",
     "https://calendar.google.com/calendar/ical/"
     "es.mexican%23holiday%40group.v.calendar.google.com/public/basic.ics"),
]


def cmd_seed(args) -> int:
    """Deja puestos los calendarios públicos (feriados): no son secreto."""
    data = load()
    added = 0
    for name, account, color, url in PUBLIC_FEEDS:
        if find(data, name):
            print(f"  ya está  {name}")
            continue
        data["calendars"].append({"name": name, "account": account or default_account(),
                                  "color": color, "url": url, "enabled": True})
        added += 1
        print(f"  puesto   {name}  ({color})")
    if added:
        save(data)
    print(f"{added} agregado(s) → {STORE}")
    return 0


def cmd_add_missing(args) -> int:
    """Recorre la lista de la Requisicion y pide, una por una, las que falten."""
    data = load()
    # los públicos (feriados) no se preguntan: se ponen solos
    for name, account, color, url in PUBLIC_FEEDS:
        if not find(data, name):
            data["calendars"].append({"name": name, "account": account or default_account(),
                                      "color": color, "url": url, "enabled": True})
            save(data)
    account = default_account()
    missing = [(n, account) for n in REQUIRED_NAMES if not find(data, n)]
    if not missing:
        print("no falta ninguna de la lista: ya están todas")
        return 0
    print(f"faltan {len(missing)} de la lista. Pega cada dirección iCal secreta y")
    print("da Enter (vacío = dejar pendiente). La dirección no se muestra.\n")
    for name, account in missing:
        url = getpass.getpass(f"  {name} ({account}): ").strip()
        if not url:
            print("    pendiente")
            continue
        data["calendars"].append({"name": name, "account": account,
                                  "color": next_color(data), "url": url,
                                  "enabled": True})
        save(data)
        print("    guardado")
    left = [n for n in REQUIRED_NAMES if not find(load(), n)]
    print(f"\nquedan pendientes: {', '.join(left) if left else 'ninguna'}")
    print("prueba con: calendar-config.py check")
    return 0


def cmd_restore(args) -> int:
    """Recupera calendarios de un respaldo, sin volver a teclear direcciones.

    Solo agrega los que faltan: si el nombre ya existe o la dirección ya está en
    otro calendario, lo salta (y lo dice). Nunca imprime la dirección.
    """
    src = Path(os.path.expanduser(args.path))
    if not src.exists():
        print(f"no encuentro {src}")
        return 1
    raw = json.loads(src.read_text(encoding="utf-8"))
    data = load()
    skip = {n.strip().lower() for n in (args.skip or "").split(",") if n.strip()}
    added = skipped = 0
    for cal in raw.get("calendars", []):
        name = cal.get("name", "")
        if not name or name.lower() in skip:
            continue
        if find(data, name):
            print(f"  ya está  {name}")
            skipped += 1
            continue
        if any(c.get("url", "").strip() == cal.get("url", "").strip()
               for c in data["calendars"]):
            print(f"  salto    {name} (la dirección ya la tiene otro calendario)")
            skipped += 1
            continue
        data["calendars"].append(dict(cal))
        added += 1
        print(f"  puesto   {name}  ({cal.get('color')})  {mask(cal.get('url',''))}")
    if added:
        save(data)
    print(f"{added} recuperado(s), {skipped} saltado(s) → {STORE}")
    return 0 if added or skipped else 1


def cmd_import(args) -> int:
    """Importa las cuentas/calendarios del plugin de Omarchy ya configurado."""
    src = Path(os.path.expanduser(args.path))
    if not src.exists():
        print(f"no encuentro {src}")
        return 1
    raw = json.loads(src.read_text(encoding="utf-8"))
    data = load()
    added = skipped = 0
    for account in raw.get("accounts", []):
        email = account.get("email", "")
        for cal in account.get("calendars", []):
            name = cal.get("name", "")
            if not name or not cal.get("url"):
                continue
            if find(data, name):
                skipped += 1
                continue
            data["calendars"].append({
                "name": name, "account": email,
                "color": cal.get("color") or account.get("color") or next_color(data),
                "url": cal["url"], "enabled": cal.get("enabled", True),
            })
            added += 1
    if added:
        save(data)
    print(f"importados {added}, ya estaban {skipped} → {STORE}")
    return 0 if added or skipped else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Calendarios iCal del tablero Monitor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="agregar un calendario")
    add.add_argument("--name", required=True)
    add.add_argument("--account", default=None, help="cuenta del calendario")
    add.add_argument("--color")
    add.add_argument("--url", help="si se omite, se pide sin mostrarla")
    add.set_defaults(fn=cmd_add)

    sub.add_parser("list", help="ver los calendarios").set_defaults(fn=cmd_list)

    col = sub.add_parser("color", help="cambiar el color de un calendario")
    col.add_argument("--name", required=True)
    col.add_argument("--color", required=True)
    col.set_defaults(fn=cmd_color)

    rm = sub.add_parser("remove", help="quitar un calendario")
    rm.add_argument("--name", required=True)
    rm.set_defaults(fn=cmd_remove)

    sub.add_parser("check", help="probar cada dirección").set_defaults(fn=cmd_check)

    sub.add_parser("seed", help="poner los calendarios públicos (feriados)"
                   ).set_defaults(fn=cmd_seed)

    sub.add_parser("add-missing",
                   help="pedir las que faltan de la lista de la Requisición"
                   ).set_defaults(fn=cmd_add_missing)

    res = sub.add_parser("restore", help="recuperar de un respaldo (sin teclear nada)")
    res.add_argument("path")
    res.add_argument("--skip", help="nombres a dejar fuera, separados por coma")
    res.set_defaults(fn=cmd_restore)

    imp = sub.add_parser("import-omarchy", help="importar del plugin de Omarchy")
    imp.add_argument("path")
    imp.set_defaults(fn=cmd_import)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
