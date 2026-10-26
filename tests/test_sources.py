#!/usr/bin/env python3
"""Pruebas de las fuentes nuevas: alertas del NWS y ruta de la escuela.

Todo con `--mock`, sin red: lo que se prueba es que el payload trae las dos
tarjetas con la forma que la página espera, y que la configuración de la
rotación/ventanas llega completa al front.

Uso:  python3 tests/test_sources.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import server  # noqa: E402

CFG = {
    "location": {"label": "test", "lat": 29.76, "lon": -95.36,
                 "timezone": "America/Chicago"},
    "week": {"days": 7, "startOffset": 0, "forecastDays": 5, "forecastStartsToday": True},
    "calendar": {"configFile": str(Path(tempfile.mkdtemp()) / "calendars.json")},
    "todoist": {"enabled": True, "tokenFile": "~/nonexistent", "project": "Shopping List",
                "pinnedCount": 2},
    "nest": {"enabled": False},
    "alerts": {"enabled": True},
    "route": {
        "enabled": True,
        "from": {"label": "Home", "lat": 29.76, "lon": -95.36},
        "to": {"label": "School", "lat": 29.71, "lon": -95.36},
        "weekdaysOnly": True,
        "windows": [
            {"start": "07:50", "end": "09:00", "label": "Drop-off"},
            {"start": "14:30", "end": "17:00", "label": "Pick-up"},
        ],
    },
    "theme": {},
}


class SourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = server.build_payload(CFG, True)

    def test_alerts_shape(self):
        alerts = self.payload["alerts"]
        self.assertEqual(alerts["count"], 1)
        first = alerts["items"][0]
        for key in ("event", "severity", "headline"):
            self.assertIn(key, first)
        self.assertTrue(self.payload["sources"]["alerts"]["ok"])

    def test_route_shape(self):
        route = self.payload["route"]
        self.assertEqual(route["min"], 13)
        self.assertEqual(route["km"], 11.2)
        self.assertEqual(route["destination"], "School")
        self.assertTrue(self.payload["sources"]["route"]["ok"])

    def test_slot_config_reaches_the_front(self):
        slot = self.payload["config"]["slot"]
        self.assertEqual(len(slot["routeWindows"]), 2)
        self.assertEqual(slot["routeWindows"][0]["start"], "07:50")
        self.assertEqual(slot["routeWindows"][1]["end"], "17:00")
        self.assertTrue(slot["routeWeekdaysOnly"])
        self.assertEqual(slot["rotateSeconds"], 300)

    def test_all_sources_are_reported(self):
        self.assertEqual(set(self.payload["sources"]),
                         {"weather", "calendar", "todoist", "nest", "alerts",
                          "route", "radar"})

    def test_radar_frame_time(self):
        radar = self.payload["radar"]
        self.assertEqual(radar["site"], "KHGX")
        self.assertIn("updatedAt", radar)
        self.assertLessEqual(radar["ageMinutes"], 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
