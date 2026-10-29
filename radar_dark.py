"""Radar del NWS en modo oscuro, sin dependencias.

El GIF de radar.weather.gov trae una sola tabla de 256 colores. En vez de
decodificar los pixeles (LZW), se reescribe SOLO la paleta: los colores del mapa
(grises, agua clara, letreros) se invierten en luminosidad conservando su tinte,
y los ecos de lluvia (colores saturados) se quedan tal cual, para que la escala
de intensidad siga leyéndose igual. Los tonos intermedios (antialias entre eco y
fondo) se mezclan suave para no dejar halos blancos.
"""
from __future__ import annotations

import time
import urllib.request

NWS_GIF = "https://radar.weather.gov/ridge/standard/{site}_0.gif"
_cache: dict = {}


def _remap(r: int, g: int, b: int) -> tuple[int, int, int]:
    mx, mn = max(r, g, b), min(r, g, b)
    sat = 0.0 if mx == 0 else (mx - mn) / mx
    lum = (r + g + b) / 3
    # mapa: luminosidad invertida hacia un pizarra oscuro, el tinte se conserva
    inv = 14 + (255 - lum) * 0.78
    dark = [inv + (c - lum) * 0.55 for c in (r, g, b)]
    dark[2] += 6                     # un pelo de azul: casa con el negro LCARS
    # qué tanto es "eco de radar": saturado y no muy oscuro
    w = min(1.0, max(0.0, (sat - 0.30) / 0.30))
    if mx < 70:                      # letreros y líneas oscuras: siempre al mapa
        w = 0.0
    out = [round(d * (1 - w) + c * w) for d, c in zip(dark, (r, g, b))]
    return tuple(max(0, min(255, v)) for v in out)


def darken_gif(data: bytes) -> bytes:
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("no es un GIF")
    buf = bytearray(data)

    def table(pos: int, n: int) -> None:
        for i in range(n):
            p = pos + 3 * i
            buf[p:p + 3] = bytes(_remap(buf[p], buf[p + 1], buf[p + 2]))

    flags = buf[10]
    i = 13
    if flags & 0x80:
        n = 2 << (flags & 7)
        table(13, n)
        i += 3 * n
    while i < len(buf):                       # tablas locales, si las hay
        t = buf[i]
        if t == 0x21:
            i += 2
            while buf[i]:
                i += buf[i] + 1
            i += 1
        elif t == 0x2C:
            f = buf[i + 9]
            i += 10
            if f & 0x80:
                n = 2 << (f & 7)
                table(i, n)
                i += 3 * n
            i += 1
            while buf[i]:
                i += buf[i] + 1
            i += 1
        else:
            break
    return bytes(buf)


def dark_radar(site: str = "KHGX", ttl: int = 240) -> tuple[bytes, str]:
    """(gif oscuro, Last-Modified del NWS). Cache corto; el último bueno se sirve si el NWS falla."""
    now = time.time()
    hit = _cache.get(site)
    if hit and now - hit[0] < ttl:
        return hit[1], hit[2]
    try:
        req = urllib.request.Request(NWS_GIF.format(site=site),
                                     headers={"User-Agent": "monitor-dashboard (home kiosk)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            lm = r.headers.get("Last-Modified", "")
        out = darken_gif(raw)
        _cache[site] = (now, out, lm)
        return out, lm
    except Exception:
        if hit:
            return hit[1], hit[2]
        raise
