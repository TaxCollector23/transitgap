from datetime import datetime
from zipfile import ZipFile
from backend.app.transit import TransitSchedule, TIMEZONE, seconds
from backend.app.transit_agencies import station_fields


def schedule(tmp_path):
    path = tmp_path / "gtfs.zip"
    with ZipFile(path, "w") as z:
        z.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name,route_color\nr,22,Test route,ff0000\n",
        )
        z.writestr(
            "trips.txt",
            "route_id,service_id,trip_id,trip_headsign\nr,weekday,t,Station\nr,special,x,Special\n",
        )
        z.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nweekday,1,1,1,1,1,0,0,20260101,20261231\n",
        )
        z.writestr(
            "calendar_dates.txt",
            "service_id,date,exception_type\nweekday,20261020,2\nspecial,20261020,1\n",
        )
        z.writestr(
            "stop_times.txt",
            "trip_id,departure_time,stop_id,pickup_type\nt,25:10:00,s,0\nx,09:00:00,s,0\nx,10:00:00,outside,0\nx,09:30:00,s,1\n",
        )
    return TransitSchedule(path, ["s"])


def test_join_calendar_exceptions_and_overnight(tmp_path):
    data = schedule(tmp_path)
    assert data.active_services(datetime(2026, 10, 20).date()) == {"special"}
    result = data.details("s", datetime(2026, 10, 20, 1, 0, tzinfo=TIMEZONE))
    assert result["routes"][0]["route_short_name"] == "22"
    assert data.routes_served("s") == ["22"]
    assert data.headsigns("s") == ["Special", "Station"]
    assert result["scheduled_departures"][0]["departure"].startswith("2026-10-20T01:10")
    assert result["scheduled_departures"][1]["headsign"] == "Special"
    assert len(result["scheduled_departures"]) == 2
    assert "outside" not in data.events
    assert result["schedule_type"] == "scheduled, not real-time"


def test_stop_description_keeps_published_direction_and_public_code():
    fields = station_fields(
        {"stop_id": "409", "stop_name": "Santa Clara & Delmas", "stop_desc": "Eastbound", "stop_code": "60409"},
        {},
        {},
        None,
        "",
    )
    assert fields["direction"] == "Eastbound"
    assert fields["stop_description"] == "Eastbound"
    assert fields["stop_code"] == "60409"


def test_cache_and_time_validation(tmp_path):
    first = schedule(tmp_path)
    second = TransitSchedule(tmp_path / "gtfs.zip", ["s"])
    assert first.events == second.events
    assert seconds("25:10:00") == 90600
    assert seconds("10:90:00") is None
    assert seconds("") is None


def test_prepared_schedule_survives_packaging_timestamp_changes(tmp_path,monkeypatch):
    import os
    from backend.app import transit
    first=schedule(tmp_path)
    path=tmp_path/'gtfs.zip'
    stamp=path.stat().st_mtime+100
    os.utime(path,(stamp,stamp))
    monkeypatch.setattr(transit,'rows',lambda *_:(_ for _ in ()).throw(AssertionError('GTFS reparsed after timestamp-only change')))
    second=TransitSchedule(path,['s'])
    assert second.cache_hit and second.events==first.events
