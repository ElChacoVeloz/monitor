#!/usr/bin/env python3
"""Resumen corto de /api/data (lo usa deploy/push-to-monitor.sh al verificar)."""
from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        print("   (no se pudo leer el JSON del tablero)")
        return 1

    fuentes = []
    for nombre, estado in (data.get("sources") or {}).items():
        if estado.get("ok"):
            fuentes.append(f"{nombre}=ok")
        else:
            fuentes.append(f"{nombre}=falla")
    print("   fuentes:", ", ".join(fuentes))

    cal = data.get("calendar") or {}
    print(f"   calendarios: {len(cal.get('calendars') or [])}"
          f" | eventos en la semana: {cal.get('eventsInWindow', '?')}"
          f" | errores: {len(cal.get('errors') or [])}")

    nest = data.get("nest") or {}
    if nest:
        print(f"   nest: {nest.get('ambientC')} °C ambiente / "
              f"{nest.get('targetC')} °C target / {nest.get('humidity')} % humedad")

    todo = data.get("todoist") or {}
    if todo:
        print(f"   lista del súper: {todo.get('count', len(todo.get('items') or []))} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
