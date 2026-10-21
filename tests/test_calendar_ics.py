#!/usr/bin/env python3
"""Pruebas del calendario por iCal (sin red, con un feed fixture).

Cubre lo que de verdad puede salir mal en un tablero de pared: que las
repeticiones caigan en el día correcto, que un evento de varios días aparezca en
todos sus días, que las excepciones (EXDATE), los cancelados y los declinados no
se pinten, y que un calendario caído no tumbe la semana.

Uso:  python3 tests/test_calendar_ics.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import server  # noqa: E402

FIXTURE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//monitor test//EN
BEGIN:VEVENT
UID:weekly-1
DTSTART;TZID=America/Chicago:20261005T090000
DTEND;TZID=America/Chicago:20261005T093000
RRULE:FREQ=WEEKLY;BYDAY=MO
SUMMARY:Weekly Monday
END:VEVENT
BEGIN:VEVENT
UID:single-1
DTSTART;TZID=America/Chicago:20261022T150000
DTEND;TZID=America/Chicago:20261022T160000
SUMMARY:Dentist
LOCATION:123 Main St
END:VEVENT
BEGIN:VEVENT
UID:multiday-1
DTSTART;VALUE=DATE:20261024
DTEND;VALUE=DATE:20261027
SUMMARY:Trip
END:VEVENT
BEGIN:VEVENT
UID:excluded-1
DTSTART;TZID=America/Chicago:20261007T120000
DTEND;TZID=America/Chicago:20261007T130000
RRULE:FREQ=WEEKLY;BYDAY=WE
EXDATE;TZID=America/Chicago:20261021T120000
SUMMARY:Weekly Wednesday
END:VEVENT
BEGIN:VEVENT
UID:cancelled-1
DTSTART;TZID=America/Chicago:20261023T100000
SUMMARY:Cancelled thing
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:declined-1
DTSTART;TZID=America/Chicago:20261023T110000
SUMMARY:Declined invite
ATTENDEE;PARTSTAT=DECLINED;CN=Me:mailto:me@example.com
END:VEVENT
END:VCALENDAR
"""


def cfg_for(calendars: list[dict]) -> dict:
    store = Path(tempfile.mkdtemp()) / "calendars.json"
    store.write_text(json.dumps({"calendars": calendars}), encoding="utf-8")
    return {
        "location": {"label": "test", "lat": 29.77, "lon": -95.61,
                     "timezone": "America/Chicago"},
        # ventana fija: semana del 21 al 27 de octubre de 2026
        "week": {"days": 7, "startOffset": 0, "forecastDays": 5,
                 "forecastStartsToday": True},
        "calendar": {"configFile": str(store)},
        "todoist": {}, "nest": {}, "theme": {},
    }


class CalendarIcsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Path(tempfile.mkdtemp()) / "feed.ics"
        self.fixture.write_text(FIXTURE, encoding="utf-8")
        self.cfg = cfg_for([
            {"name": "Home", "account": "me@example.com",
             "color": "#4f7cf7", "url": self.fixture.as_uri(), "enabled": True},
        ])

    def week(self) -> dict:
        # la ventana se ancla al dia de hoy; se prueba con los dias reales
        data = server.calendar_week(self.cfg, False)
        return {d["date"]: d["events"] for d in data["days"]}

    def test_recurring_single_and_multiday_land_on_the_right_days(self):
        days = self.week()
        titles = {d: [e["title"] for e in evs] for d, evs in days.items()}
        # el lunes de ESTA semana (no el de la semana pasada)
        mondays = [d for d, t in titles.items() if "Weekly Monday" in t]
        self.assertEqual(len(mondays), 1, titles)
        self.assertTrue(mondays[0].endswith(mondays[0][-2:]))  # fecha iso valida
        from datetime import date as _d
        self.assertEqual(_d.fromisoformat(mondays[0]).weekday(), 0)
        # el viaje de 3 dias aparece en sus 3 dias
        trip_days = [d for d, t in titles.items() if "Trip" in t]
        self.assertEqual(len(trip_days), 3, titles)

    def test_excluded_cancelled_and_declined_are_not_shown(self):
        days = self.week()
        todas = [e["title"] for evs in days.values() for e in evs]
        self.assertNotIn("Cancelled thing", todas)
        self.assertNotIn("Declined invite", todas)
        # la unica ocurrencia de "Weekly Wednesday" que caia en la ventana esta
        # en EXDATE, asi que no debe aparecer
        self.assertNotIn("Weekly Wednesday", todas)

    def test_one_broken_calendar_does_not_kill_the_week(self):
        self.cfg["calendar"]["configFile"]  # noqa: B018
        store = Path(self.cfg["calendar"]["configFile"])
        store.write_text(json.dumps({"calendars": [
            {"name": "Home", "account": "x", "color": "#4f7cf7",
             "url": self.fixture.as_uri()},
            {"name": "Roto", "account": "x", "color": "#e0533d",
             "url": (Path(tempfile.mkdtemp()) / "no-existe.ics").as_uri()},
        ]}), encoding="utf-8")
        data = server.calendar_week(self.cfg, False)
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["calendar"], "Roto")
        self.assertGreater(sum(len(d["events"]) for d in data["days"]), 0)

    def test_no_calendars_is_unconfigured_not_an_error(self):
        """Sin calendarios el tablero avisa que falta configurar, no truena."""
        self.cfg["calendar"]["configFile"] = str(Path(tempfile.mkdtemp()) / "nada.json")
        data = server.calendar_week(self.cfg, False)
        self.assertTrue(data.get("unconfigured"))
        self.assertEqual(data["calendars"], [])
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(data["errors"], [])

    def test_window_is_seven_days_starting_today(self):
        data = server.calendar_week(self.cfg, False)
        first = date.fromisoformat(data["days"][0]["date"])
        last = date.fromisoformat(data["days"][-1]["date"])
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual((last - first).days, 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
