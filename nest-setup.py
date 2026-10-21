#!/usr/bin/env python3
"""Conectar el termostato Nest al tablero (Google Device Access / SDM).

Son cuatro pasos, en este orden. El script hace los tres ultimos y guarda todo
donde `server.py` lo espera; lo unico que no puede hacer por ti es el papeleo en
el navegador.

  1. (una vez, en la consola) Proyecto de Device Access + cliente OAuth
     "Web application" con redirect URI https://www.google.com, y ese client ID
     capturado en el proyecto de Device Access. El Smart Device Management API
     tiene que estar habilitado en el proyecto de Google Cloud.

  2. nest-setup.py client --json ~/Downloads/client_secret_XXXX.json
        guarda client_id/client_secret en ~/.hermes/nest_client.json (600)

  3. nest-setup.py url
        imprime la URL de autorizacion: abrela, acepta los permisos del termostato
        y pega de vuelta la URL de https://www.google.com?code=... (falla la
        pantalla, es normal)

     nest-setup.py code "<url o codigo>"
        canjea el codigo y guarda el refresh token en ~/.hermes/nest_token.json

  4. nest-setup.py devices
        lista los dispositivos del proyecto; si hay un solo termostato, escribe
        su deviceId en config.json y deja nest.enabled = true

  nest-setup.py status
        dice que falta (sirve para retomar despues)

El deviceId es el que "no se ve" en la consola: sale de la llamada devices.list,
y por eso hay que autorizar antes de poder preguntarlo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config.json"
CLIENT_FILE = Path.home() / ".hermes" / "nest_client.json"
TOKEN_FILE = Path.home() / ".hermes" / "nest_token.json"
# Google documenta https://www.google.com, pero el redirect tiene que ser uno de
# los registrados en el cliente OAuth: se toma del JSON del cliente y, si no hay
# ninguno de Google, se cae al documentado.
REDIRECT_CANDIDATES = ("https://www.google.com", "https://google.com")
REDIRECT = "https://www.google.com"
SCOPE = "https://www.googleapis.com/auth/sdm.service"
AUTH_BASE = "https://nestservices.google.com/partnerconnections/{pid}/auth"
DEVICES_API = "https://smartdevicemanagement.googleapis.com/v1/enterprises/{pid}/devices"
TOKEN_APIS = ["https://oauth2.googleapis.com/token",
              "https://www.googleapis.com/oauth2/v4/token"]


def log(msg: str = "") -> None:
    print(msg, flush=True)


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_private(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def pick_redirect(registered: list[str] | None) -> str:
    """El redirect que de verdad acepta el cliente OAuth."""
    registered = [r.rstrip("/") for r in (registered or [])]
    for candidate in REDIRECT_CANDIDATES:
        if candidate in registered:
            return candidate
    return REDIRECT


def redirect_uri(client: dict | None = None) -> str:
    client = client if client is not None else (read_json(CLIENT_FILE) or {})
    return client.get("redirect_uri") or REDIRECT


def project_id(cli_value: str | None = None) -> str:
    if cli_value:
        return cli_value
    cfg = read_json(CONFIG) or {}
    pid = (cfg.get("nest") or {}).get("projectId") or ""
    if not pid:
        log("falta el projectId: ponlo en config.json (nest.projectId) o pasa --project-id")
        sys.exit(2)
    return pid


def http(url: str, *, method: str = "GET", headers: dict | None = None,
         form: dict | None = None, timeout: int = 30) -> tuple[int, dict | str]:
    data = urllib.parse.urlencode(form).encode() if form else None
    hdrs = dict(headers or {})
    if data:
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, headers=hdrs,
                                 method="POST" if data else method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            code = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        code = exc.code
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"
    try:
        return code, json.loads(body)
    except ValueError:
        return code, body[:400]


def cmd_client(args) -> int:
    blob: dict = {}
    if args.json:
        raw = read_json(Path(os.path.expanduser(args.json)))
        if not raw:
            log(f"no pude leer {args.json}")
            return 2
        blob = raw.get("web") or raw.get("installed") or raw
        client_id, client_secret = blob.get("client_id"), blob.get("client_secret")
    else:
        client_id, client_secret = args.client_id, args.client_secret
        blob = {"client_id": client_id}
    if not client_id or not client_secret:
        log("faltan client_id/client_secret: usa --json <credenciales.json>")
        return 2
    registered = blob.get("redirect_uris") if args.json else None
    redirect = pick_redirect(registered)
    write_private(CLIENT_FILE, {"client_id": client_id, "client_secret": client_secret,
                                "redirect_uri": redirect,
                                "registered_redirects": registered or [],
                                "saved": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    kind = "web" if blob.get("client_secret") else "?"
    log(f"cliente guardado en {CLIENT_FILE} (600) — {client_id[:18]}… ({kind})")
    if registered:
        log(f"redirects registrados: {', '.join(registered)}")
        if redirect != "https://www.google.com":
            log(f"ojo: se usará {redirect} (el que está registrado); Google documenta "
                "https://www.google.com, así que si el flujo falla al final, agrega "
                "https://www.google.com en las redirect URIs del cliente")
    log("recuerda: el client ID de este cliente tiene que estar capturado en el "
        "proyecto de Device Access")
    return 0


def cmd_url(args) -> int:
    client = read_json(CLIENT_FILE)
    if not client:
        log("primero: nest-setup.py client --json <credenciales.json>")
        return 2
    pid = project_id(args.project_id)
    query = urllib.parse.urlencode({
        "redirect_uri": redirect_uri(client), "access_type": "offline", "prompt": "consent",
        "client_id": client["client_id"], "response_type": "code", "scope": SCOPE,
    })
    log(AUTH_BASE.format(pid=pid) + "?" + query)
    log()
    log("Abre esa URL (con la cuenta de Google del termostato), acepta los permisos")
    log("del termostato y copia la URL a la que te mande; luego:")
    log('  nest-setup.py code "https://www.google.com?code=..."')
    return 0


def cmd_code(args) -> int:
    client = read_json(CLIENT_FILE)
    if not client:
        log("primero: nest-setup.py client --json <credenciales.json>")
        return 2
    code = args.value.strip()
    if "code=" in code:
        parsed = urllib.parse.urlparse(code)
        params = urllib.parse.parse_qs(parsed.query)
        code = (params.get("code") or [""])[0]
    if not code:
        log("no encontre el codigo en lo que pegaste")
        return 2
    form = {"client_id": client["client_id"], "client_secret": client["client_secret"],
            "code": code, "grant_type": "authorization_code",
            "redirect_uri": redirect_uri(client)}
    last = None
    for url in TOKEN_APIS:
        status, payload = http(url, form=form)
        if status == 200 and isinstance(payload, dict) and payload.get("refresh_token"):
            write_private(TOKEN_FILE, {
                "client_id": client["client_id"], "client_secret": client["client_secret"],
                "refresh_token": payload["refresh_token"],
                "scope": payload.get("scope", SCOPE),
                "obtained": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            log(f"refresh token guardado en {TOKEN_FILE} (600)")
            log("siguiente: nest-setup.py devices")
            return 0
        last = (status, payload)
        if isinstance(payload, dict) and payload.get("error") == "invalid_grant":
            break
    log(f"no se pudo canjear el codigo: {last}")
    log("el codigo caduca en minutos y solo sirve una vez: genera otra URL con "
        "'nest-setup.py url' y repite")
    return 1


def access_token() -> str | None:
    tok = read_json(TOKEN_FILE)
    if not tok:
        return None
    form = {"client_id": tok["client_id"], "client_secret": tok["client_secret"],
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}
    for url in TOKEN_APIS:
        status, payload = http(url, form=form)
        if status == 200 and isinstance(payload, dict) and payload.get("access_token"):
            return payload["access_token"]
    log("no pude refrescar el token: vuelve a autorizar con 'nest-setup.py url'")
    return None


def cmd_devices(args) -> int:
    pid = project_id(args.project_id)
    token = access_token()
    if not token:
        log("falta autorizar: nest-setup.py url / code")
        return 2
    status, payload = http(DEVICES_API.format(pid=pid),
                           headers={"Authorization": f"Bearer {token}"})
    if status != 200 or not isinstance(payload, dict):
        log(f"devices.list respondio {status}: {payload}")
        return 1
    devices = payload.get("devices", [])
    if not devices:
        log("el proyecto no tiene dispositivos autorizados. En la pantalla de")
        log("permisos de Nest hay que marcar el termostato (y su casa) antes de dar Allow.")
        return 1
    thermostats = []
    log(f"{len(devices)} dispositivo(s):\n")
    for dev in devices:
        traits = dev.get("traits", {})
        info = traits.get("sdm.devices.traits.Info", {})
        kind = dev.get("type", "").rsplit(".", 1)[-1]
        name = info.get("customName") or "(sin nombre)"
        log(f"  {dev.get('name','')}")
        log(f"    tipo: {kind}   nombre: {name}")
        if kind == "THERMOSTAT":
            temp = traits.get("sdm.devices.traits.Temperature", {})
            if temp:
                log(f"    ambiente: {temp.get('ambientTemperatureCelsius')} °C")
            thermostats.append((dev, kind))
    if len(thermostats) == 1 and not args.no_write:
        dev, _ = thermostats[0]
        cfg = read_json(CONFIG) or {}
        nest = cfg.setdefault("nest", {})
        nest["projectId"] = pid
        nest["deviceId"] = dev.get("name", "").rsplit("/", 1)[-1]
        nest["enabled"] = True
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"\nlisto: deviceId guardado en config.json y nest.enabled = true")
        log("reinicia el tablero (o espera 2 minutos) y la tarjeta se llena sola")
    elif len(thermostats) > 1:
        log("\nhay varios termostatos: copia el deviceId que quieras a config.json "
            "(nest.deviceId) y pon nest.enabled = true")
    return 0


def cmd_status(args) -> int:
    cfg = read_json(CONFIG) or {}
    nest = cfg.get("nest") or {}
    client = read_json(CLIENT_FILE)
    token = read_json(TOKEN_FILE)
    log("estado del Nest:\n")
    log(f"  projectId     {'sí  ' + nest.get('projectId', '') if nest.get('projectId') else 'FALTA'}")
    log(f"  cliente OAuth {'sí  ' + client['client_id'][:18] + '…' if client else 'FALTA  (nest-setup.py client --json ...)'}")
    log(f"  refresh token {'sí' if token else 'FALTA  (nest-setup.py url / code)'}")
    log(f"  deviceId      {'sí  ' + nest.get('deviceId', '') if nest.get('deviceId') else 'FALTA  (nest-setup.py devices)'}")
    log(f"  habilitado    {'sí' if nest.get('enabled') else 'no'}")
    if all([nest.get("projectId"), client, token, nest.get("deviceId")]):
        log("\nsi todo está en verde y la tarjeta sigue vacía: revisa el log del tablero")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Conectar el Nest al tablero (SDM)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("client", help="guardar el cliente OAuth del proyecto")
    c.add_argument("--json", help="credenciales descargadas de Google Cloud")
    c.add_argument("--client-id")
    c.add_argument("--client-secret")
    c.set_defaults(fn=cmd_client)

    u = sub.add_parser("url", help="imprimir la URL de autorización")
    u.add_argument("--project-id")
    u.set_defaults(fn=cmd_url)

    k = sub.add_parser("code", help="canjear el código por el refresh token")
    k.add_argument("value")
    k.set_defaults(fn=cmd_code)

    d = sub.add_parser("devices", help="listar dispositivos y guardar el deviceId")
    d.add_argument("--project-id")
    d.add_argument("--no-write", action="store_true", help="solo listar")
    d.set_defaults(fn=cmd_devices)

    sub.add_parser("status", help="qué falta").set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
