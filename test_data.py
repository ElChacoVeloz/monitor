#!/usr/bin/env python3
"""Banco de pruebas: sirve el tablero con datos alterados a proposito.

Toma el JSON real del servidor (http://127.0.0.1:8770/api/data) y le aplica un
escenario, para ver como se comporta la pagina sin tocar nada de verdad.

Uso:  python3 test_data.py <puerto> <escenario>
Escenarios:
  bigshop      la lista del super con 22 items
  busyday      un dia con 9 eventos (prueba de apretado de columnas)
  noevents     semana sin ningun evento
  limits       amanecer 2 min atras / anochecer en 6 h (prueba de paleta)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

PORT = int(sys.argv[1])
SCENARIO = sys.argv[2] if len(sys.argv) > 2 else "bigshop"
TZ = ZoneInfo("America/Chicago")
WEB = Path(__file__).resolve().parent / "web"

base = json.loads(urllib.request.urlopen("http://127.0.0.1:8770/api/data", timeout=15).read())

if SCENARIO == "bigshop":
    items = [{"id": "1", "content": "Milk", "pinned": True},
             {"id": "2", "content": "Eggs", "pinned": True}]
    for n in range(1, 21):
        items.append({"id": str(n + 2), "content": f"Item de prueba {n}",
                      "pinned": False})
    base["todoist"] = {"project": "Lista del Super 🛒", "items": items,
                       "count": len(items), "pinnedCount": 2}
elif SCENARIO == "busyday":
    day = base["calendar"]["days"][1]
    day["events"] = [{"id": str(i), "calendar": "Trabajo", "title": f"Evento {i}",
                      "location": "123 Main St", "allDay": False, "color": "#e0533d",
                      "start": f"{day['date']}T{8 + i:02d}:00:00-05:00", "end": None}
                     for i in range(9)]
elif SCENARIO == "noevents":
    for day in base["calendar"]["days"]:
        day["events"] = []
elif SCENARIO == "limits":
    now = datetime.now(TZ)
    base["weather"]["sun"]["sunrise"] = (now - timedelta(minutes=2)).replace(
        tzinfo=None).isoformat(timespec="minutes")
    base["weather"]["sun"]["sunset"] = (now + timedelta(hours=6)).replace(
        tzinfo=None).isoformat(timespec="minutes")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]   # ?theme=day|night viaja en la query
        if path.startswith("/api/data"):
            body, ctype = json.dumps(base).encode(), "application/json"
        else:
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            f = WEB / name
            if not f.exists():
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = f.read_bytes()
            ctype = ("text/css" if name.endswith(".css") else
                     "application/javascript" if name.endswith(".js") else "text/html")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


print(f"banco de pruebas en :{PORT} — escenario {SCENARIO}")
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
