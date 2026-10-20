import { useEffect, useState } from "react";
import { studySummary, stopAccess, civicLetter } from "./data";
export type GapDetail = {
  stop_id: string;
  stop_name: string;
  latitude: number;
  longitude: number;
  gap_score: number | null;
  standard: { reachable_length_m: number; geometry: GeoJSON.Geometry };
  wheelchair: { reachable_length_m: number; geometry: GeoJSON.Geometry };
  wheelchair_boarding: number;
  warning: string;
};
type Item = { properties: GapDetail };
export default function GapPanel({
  onStudy,
}: {
  onStudy: (detail: GapDetail | null) => void;
}) {
  const [items, setItems] = useState<Item[]>([]),
    [count, setCount] = useState(0),
    [detail, setDetail] = useState<GapDetail | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [letter, setLetter] = useState("");
  async function select(id: string) {
    setBusy(true);
    setError("");
    setLetter("");
    try {
      const data = await stopAccess(id);
      setDetail(data);
      onStudy(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unavailable");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    studySummary(10, controller.signal)
      .then((data) => {
        setItems(data.features);
        setCount(data.evaluated_stop_count);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    const id = new URLSearchParams(location.search).get("stop");
    if (id) void select(id);
    return () => controller.abort();
  }, []);
  return (
    <section className="gap-study" aria-label="Stop access gap study">
      <h2>Ten-minute access gaps</h2>
      <p>
        Measured differences in reachable walking-network length, using standard
        and wheelchair profiles. This ranking covers{" "}
        {count || "the available sample of"} evaluated stops, not every county
        stop.
      </p>
      <p>
        Different assumed speeds, 2.7 and 2.0 mph, and mapped constraints both
        affect the results. Missing data is not a confirmed barrier.
      </p>
      {error && <p role="alert">{error}</p>}
      {busy && (
        <p role="status">
          <span className="spinner" /> Computing network reach…
        </p>
      )}
      <h3>Largest gaps in the sample</h3>
      <ol className="gap-ranking">
        {items.map(({ properties: p }, i) => (
          <li key={p.stop_id}>
            <button className="list-row" onClick={() => void select(p.stop_id)}>
              <span>
                {i + 1}. {p.stop_name}
              </span>
              <strong>
                {p.gap_score === null
                  ? "Unavailable"
                  : `${Math.round(p.gap_score * 100)}%`}
              </strong>
            </button>
          </li>
        ))}
      </ol>
      {detail && (
        <article className="study-detail">
          <h3>{detail.stop_name}</h3>
          <dl>
            <div>
              <dt>Standard network</dt>
              <dd>
                {(detail.standard.reachable_length_m / 1609.344).toFixed(2)} mi
              </dd>
            </div>
            <div>
              <dt>Wheelchair model</dt>
              <dd>
                {(detail.wheelchair.reachable_length_m / 1609.344).toFixed(2)}{" "}
                mi
              </dd>
            </div>
            <div>
              <dt>Boarding status in GTFS</dt>
              <dd>
                {detail.wheelchair_boarding === 1
                  ? "Accessible boarding recorded"
                  : detail.wheelchair_boarding === 2
                    ? "Not accessible recorded"
                    : "Unknown"}
              </dd>
            </div>
          </dl>
          <p>
            Grey paths: standard reach. Green paths: wheelchair-profile reach.
            The networks follow mapped paths toward this stop and are clipped to
            the county boundary.
          </p>
          <p>{detail.warning}</p>
          <button
            className="button"
            onClick={async () => {
              try {
                setLetter(await civicLetter(detail.stop_id));
              } catch (e) {
                setError(e instanceof Error ? e.message : "Unavailable");
              }
            }}
          >
            Prepare a letter
          </button>
          {letter && (
            <div className="letter-editor">
              <label htmlFor="civic-letter">
                Review and edit before sending
              </label>
              <textarea
                id="civic-letter"
                rows={14}
                value={letter}
                onChange={(e) => setLetter(e.target.value)}
              />
              <button
                className="button"
                onClick={() => {
                  const blob = new Blob([letter], { type: "text/plain" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `transitgap-stop-${detail.stop_id}.txt`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                Download draft
              </button>
              <p>This draft has not been sent.</p>
            </div>
          )}
        </article>
      )}
    </section>
  );
}
