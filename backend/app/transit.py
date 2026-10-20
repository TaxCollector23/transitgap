"""Streaming GTFS joins and service-aware scheduled departures, never live arrivals."""

from __future__ import annotations
import csv
import gzip
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from zipfile import ZipFile
from .data_loader import data_dir

TIMEZONE = ZoneInfo("America/Los_Angeles")


def rows(archive, name):
    if name not in archive.namelist():
        return
    with archive.open(name) as source:
        yield from csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))


def seconds(value):
    try:
        h, m, s = map(int, value.split(":"))
        return h * 3600 + m * 60 + s if h >= 0 and 0 <= m < 60 and 0 <= s < 60 else None
    except (ValueError, AttributeError):
        return None


class TransitSchedule:
    def __init__(self, archive_path: Path, stop_ids, cache_path: Path | None = None):
        self.routes, self.trips, self.calendar, self.exceptions, self.events = (
            {},
            {},
            {},
            {},
            {},
        )
        self.feed_info = []
        cache_path = cache_path or archive_path.with_name("schedule-v1.json.gz")
        signature = [
            archive_path.stat().st_size,
            archive_path.stat().st_mtime_ns,
            sorted(stop_ids),
        ]
        if cache_path.exists():
            try:
                with gzip.open(cache_path, "rt") as source:
                    cached = json.load(source)
                if cached["signature"] == signature:
                    self.__dict__.update(cached["schedule"])
                    return
            except (OSError, ValueError, KeyError):
                pass
        selected = set(stop_ids)
        with ZipFile(archive_path) as archive:
            self.routes = {
                r["route_id"]: {
                    k: r.get(k, "")
                    for k in (
                        "route_id",
                        "route_short_name",
                        "route_long_name",
                        "route_color",
                        "route_text_color",
                    )
                }
                for r in rows(archive, "routes.txt")
            }
            self.trips = {
                r["trip_id"]: [
                    r["route_id"],
                    r["service_id"],
                    r.get("trip_headsign", ""),
                ]
                for r in rows(archive, "trips.txt")
            }
            self.calendar = {r["service_id"]: r for r in rows(archive, "calendar.txt")}
            for row in rows(archive, "calendar_dates.txt"):
                self.exceptions.setdefault(row["date"], {})[row["service_id"]] = int(
                    row["exception_type"]
                )
            self.feed_info = list(rows(archive, "feed_info.txt"))
            # Stream stop_times and retain only loaded stops, compact scalar records.
            for row in rows(archive, "stop_times.txt"):
                stop_id = row["stop_id"]
                value = seconds(row.get("departure_time", ""))
                if (
                    stop_id in selected
                    and value is not None
                    and row["trip_id"] in self.trips
                    and row.get("pickup_type", "0") != "1"
                ):
                    self.events.setdefault(stop_id, []).append([value, row["trip_id"]])
        for events in self.events.values():
            events.sort()
        try:
            temporary = cache_path.with_suffix(".part")
            with gzip.open(temporary, "wt") as output:
                json.dump(
                    {"signature": signature, "schedule": self.__dict__},
                    output,
                    separators=(",", ":"),
                )
            temporary.replace(cache_path)
        except OSError:
            pass  # A bundled runtime may be read-only.

    def active_services(self, date):
        key = date.strftime("%Y%m%d")
        weekday = date.strftime("%A").lower()
        active = {
            service
            for service, row in self.calendar.items()
            if row["start_date"] <= key <= row["end_date"] and row.get(weekday) == "1"
        }
        for service, kind in self.exceptions.get(key, {}).items():
            active.add(service) if kind == 1 else active.discard(service)
        return active

    def details(self, stop_id, now=None):
        now = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
        events = self.events.get(stop_id, [])
        serving = sorted({self.trips[trip][0] for _, trip in events})
        departures = []
        # Yesterday covers GTFS 24:xx/25:xx times. Include tomorrow for late-night queries.
        for offset in (-1, 0, 1):
            date = now.date() + timedelta(days=offset)
            active = self.active_services(date)
            midnight = datetime.combine(date, datetime.min.time(), tzinfo=TIMEZONE)
            for value, trip_id in events:
                route_id, service_id, headsign = self.trips[trip_id]
                if service_id not in active:
                    continue
                departure = midnight + timedelta(seconds=value)
                if now <= departure <= now + timedelta(hours=24):
                    departures.append(
                        {
                            "departure": departure.isoformat(),
                            "route": self.routes.get(route_id),
                            "headsign": headsign,
                            "trip_id": trip_id,
                        }
                    )
        departures.sort(key=lambda e: e["departure"])
        return {
            "routes": [self.routes[r] for r in serving if r in self.routes],
            "scheduled_departures": departures[:3],
            "schedule_type": "scheduled, not real-time",
            "timezone": str(TIMEZONE),
            "queried_at": now.isoformat(),
            "feed_info": self.feed_info,
            "message": None
            if departures
            else "No scheduled departure found in the next 24 hours in this feed.",
        }
