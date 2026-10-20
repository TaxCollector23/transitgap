import { useEffect, useState } from "react";
const API =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "" : "http://localhost:8000");
export default function StopService({ id }: { id: string }) {
  const [data, setData] = useState<{
    wheelchair_boarding: number;
    service: {
      routes: Array<{
        route_id: string;
        route_short_name: string;
        route_long_name: string;
      }>;
      scheduled_departures: Array<{
        departure: string;
        headsign: string;
        trip_id: string;
        route: { route_short_name: string };
      }>;
    };
  } | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setData(null);
    setFailed(false);
    const c = new AbortController();
    fetch(`${API}/stops/${encodeURIComponent(id)}`, { signal: c.signal })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then(setData)
      .catch(() => {
        if (!c.signal.aborted) setFailed(true);
      });
    return () => c.abort();
  }, [id]);
  return (
    <details className="plain-details">
      <summary>Stop service & boarding</summary>
      {failed ? (
        <p>Schedule unavailable.</p>
      ) : !data ? (
        <p>Loading schedule…</p>
      ) : (
        <>
          <p>
            Stop {id}. Boarding:{" "}
            {data.wheelchair_boarding === 1
              ? "accessible boarding recorded"
              : data.wheelchair_boarding === 2
                ? "not accessible recorded"
                : "unknown"}
            .
          </p>
          {data.service ? (
            <>
              <p>
                Routes:{" "}
                {data.service.routes
                  .map((r) => r.route_short_name || r.route_long_name)
                  .join(", ") || "Unavailable"}
              </p>
              <h4>Scheduled, not real-time</h4>
              <ul>
                {data.service.scheduled_departures.map((d) => (
                  <li key={`${d.trip_id}${d.departure}`}>
                    {new Date(d.departure).toLocaleTimeString("en-US", {
                      hour: "numeric",
                      minute: "2-digit",
                      timeZone: "America/Los_Angeles",
                    })}{" "}
                    · {d.route?.route_short_name} · {d.headsign}
                  </li>
                ))}
              </ul>
              {data.service.scheduled_departures.length === 0 && (
                <p>No departures found in the next 24 hours in this feed.</p>
              )}
            </>
          ) : (
            <p>Schedule unavailable.</p>
          )}
        </>
      )}
    </details>
  );
}
