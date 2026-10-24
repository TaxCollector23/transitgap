import { useEffect, useState } from "react";
import { API } from "./data";
import type { Place } from "./format";
import type { Stop } from "./types";

type Service = {
  agency: string;
  agency_url: string;
  schedule_url?: string;
  wheelchair_boarding: number;
  station_url?: string | null;
  service: {
    routes: Array<{ route_id: string; route_short_name: string; route_long_name: string }>;
    scheduled_departures: Array<{
      departure: string;
      headsign: string;
      trip_id: string;
      route: { route_short_name: string; route_long_name?: string } | null;
    }>;
    feed_info: Array<{ feed_end_date?: string; feed_start_date?: string }>;
    schedule_validity?: { status: string; message: string | null };
    message?: string | null;
  } | null;
};

function boarding(value: number | undefined, agency: string) {
  if (value === 1) return "Accessible boarding is recorded in the agency's data.";
  if (value === 2) return "The agency's data records boarding here as not accessible.";
  return `${agency}'s data doesn't record whether boarding here is accessible.`;
}

function pacificToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date()).replace(/-/g, "");
}

function displayFeedDate(value?: string) {
  return value && /^\d{8}$/.test(value)
    ? `${value.slice(4, 6)}/${value.slice(6, 8)}/${value.slice(0, 4)}`
    : value || "not stated";
}

function PlatformService({ stop, label }: { stop: Stop; label: string | null }) {
  const [data, setData] = useState<Service | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setData(null);
    setFailed(false);
    const c = new AbortController();
    fetch(`${API}/stops/${encodeURIComponent(stop.stop_id)}`, { signal: c.signal })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then(setData)
      .catch(() => {
        if (!c.signal.aborted) setFailed(true);
      });
    return () => c.abort();
  }, [stop.stop_id]);
  if (failed) return <p>Schedule information is unavailable right now.</p>;
  if (!data) return <p role="status">Loading schedule…</p>;
  const service = data.service;
  // Older API responses carry only feed_info; apply the same rule locally.
  const feedEnd = service?.feed_info?.[0]?.feed_end_date;
  const feedStart = service?.feed_info?.[0]?.feed_start_date;
  const today = pacificToday();
  const validity = service?.schedule_validity?.status ??
    (feedStart && feedStart > today ? "not_yet_valid" : feedEnd && feedEnd < today ? "expired" : "current");
  const scheduleLink = data.schedule_url || data.agency_url;
  return (
    <div className="platform-service">
      {label && <h4>{label}</h4>}
      <p>{boarding(data.wheelchair_boarding, data.agency)}</p>
      {service ? (
        <>
          <p>
            Routes: {service.routes.map((r) => r.route_short_name || r.route_long_name).join(", ") || "Not listed in the feed"}
          </p>
          {validity === "not_yet_valid" || validity === "expired" ? (
            <p>
              This timetable doesn't cover today. The loaded feed covers {displayFeedDate(feedStart)} to {displayFeedDate(feedEnd)}. {" "}
              <a href={scheduleLink} target="_blank" rel="noreferrer">Check {data.agency} for current times</a>.
            </p>
          ) : service.scheduled_departures.length ? (
            <>
              <p>Next scheduled departures (from the published timetable, not live):</p>
              <ul>
                {service.scheduled_departures.map((d) => (
                  <li key={`${d.trip_id}${d.departure}`}>
                    {new Date(d.departure).toLocaleTimeString("en-US", {
                      hour: "numeric", minute: "2-digit", timeZone: "America/Los_Angeles",
                    })}{" "}
                    · {d.route?.route_short_name || d.route?.route_long_name} · {d.headsign}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p>No departures in the next 24 hours in the published timetable.</p>
          )}
        </>
      ) : (
        <p>Schedule information is unavailable right now.</p>
      )}
    </div>
  );
}

export default function StopService({ place, selectedStopId }: { place: Place; selectedStopId?: string }) {
  const stops = place.stops;
  const first = stops[0];
  const entrances = first.entrances || [];
  return (
    <div className="stop-service">
      {stops.map((stop) => (
        <PlatformService
          key={stop.stop_id}
          stop={stop}
          label={stops.length > 1 ? stop.platform_name || stop.stop_name : place.duplicateName && stop.stop_id === selectedStopId ? place.disambiguation : null}
        />
      ))}
      {entrances.length > 0 && (
        <>
          <h4>Station entrances in the agency's data</h4>
          <ul>
            {entrances.map((entrance) => (
              <li key={entrance.entrance_id}>
                {entrance.name}
                {entrance.wheelchair_boarding === 1 ? " · step-free access recorded" : entrance.wheelchair_boarding === 2 ? " · recorded as not step-free" : ""}
              </li>
            ))}
          </ul>
        </>
      )}
      {first.station_url && (
        <p>
          <a href={first.station_url} target="_blank" rel="noreferrer">Agency station page</a>
        </p>
      )}
    </div>
  );
}
