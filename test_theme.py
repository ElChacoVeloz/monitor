#!/usr/bin/env python3
"""Prueba del cambio de paleta: sirve /api/data con amanecer/anochecer movidos.

Uso:  python3 test_theme.py <puerto> <sunrise|sunset> <minutos_relativos>
Ej:   python3 test_theme.py 8772 sunset -2   -> el sol se puso hace 2 min (noche)
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

PORT = int(sys.argv[1])
WHICH = sys.argv[2]
OFFSET = int(sys.argv[3])
TZ = ZoneInfo("America/Chicago")

base = json.loads(urllib.request.urlopen("http://127.0.0.1:8770/api/data", timeout=10).read())
now = datetime.now(TZ)
stamp = (now + timedelta(minutes=OFFSET)).replace(tzinfo=None).isoformat(timespec="minutes")
base["weather"]["sun"][WHICH] = stamp
if WHICH == "sunrise":
    base["weather"]["sun"]["sunset"] = (now + timedelta(hours=6)).replace(tzinfo=None).isoformat(timespec="minutes")
else:
    base["weather"]["sun"]["sunrise"] = (now - timedelta(hours=6)).replace(tzinfo=None).isoformat(timespec="minutes")

WEB = Path(__file__).resolve().parent / "web"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]   # ?theme=day|night viaja en la query
        if path.startswith("/api/data"):
            body = json.dumps(base).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            p = "index.html" if path in ("/", "") else path.lstrip("/")
            f = WEB / p
            if not f.exists():
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             "text/css" if p.endswith(".css") else
                             "application/javascript" if p.endswith(".js") else "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


print(f"stub en :{PORT}  {WHICH}={stamp}")
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
