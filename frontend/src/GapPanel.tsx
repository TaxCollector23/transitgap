import { useEffect, useState } from "react";
import { studySummary, stopAccess, civicLetter, reachabilityStops, stopReachability } from "./data";
import type { ReachabilityAnalysis, ReachabilityStop } from "./types";
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
  onReachability,
}: {
  onStudy: (detail: GapDetail | null) => void;
  onReachability: (analysis: ReachabilityAnalysis | null, layers: { documented: boolean; unknown: boolean }) => void;
}) {
  const [items, setItems] = useState<Item[]>([]),
    [count, setCount] = useState(0),
    [detail, setDetail] = useState<GapDetail | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [letter, setLetter] = useState("");
  const [summaryBusy, setSummaryBusy] = useState(true);
  const [pilotStops, setPilotStops] = useState<ReachabilityStop[]>([]);
  const [pilotStopId, setPilotStopId] = useState("");
  const [reachProfile, setReachProfile] = useState("wheelchair");
  const [reachMinutes, setReachMinutes] = useState(10);
  const [reachability, setReachability] = useState<ReachabilityAnalysis | null>(null);
  const [reachBusy, setReachBusy] = useState(false);
  const [reachError, setReachError] = useState("");
  const [showDocumented, setShowDocumented] = useState(false);
  const [showUnknown, setShowUnknown] = useState(false);
  useEffect(() => {
    reachabilityStops()
      .then((data) => {
        setPilotStops(data.stops);
        const connected = (data.stops as ReachabilityStop[]).find((stop) => typeof stop.connector_distance_m === "number" && stop.connector_distance_m <= 35);
        setPilotStopId(connected?.stop_id || data.stops[0]?.stop_id || "");
      })
      .catch((e) => setReachError(e instanceof Error ? e.message : "Pilot data unavailable."));
  }, []);
  async function analyzeReachability() {
    if (!pilotStopId) return;
    setReachBusy(true);
    setReachError("");
    setReachability(null);
    onStudy(null);
    try {
      const data = await stopReachability(pilotStopId, reachProfile, reachMinutes) as ReachabilityAnalysis;
      const documented = data.status !== "STOP_CONNECTION_UNKNOWN" && data.documented.reachable_edge_count > 0;
      const unknown = data.status !== "STOP_CONNECTION_UNKNOWN" && data.unknown_gap.edge_count > 0;
      setReachability(data);
      setShowDocumented(documented);
      setShowUnknown(unknown);
      onReachability(data, { documented, unknown });
    } catch (e) {
      setReachError(e instanceof Error ? e.message : "Reachability study unavailable.");
    } finally {
      setReachBusy(false);
    }
  }
  function updateLayers(documented: boolean, unknown: boolean) {
    setShowDocumented(documented);
    setShowUnknown(unknown);
    if (reachability) onReachability(reachability, { documented, unknown });
  }
  async function select(id: string) {
    setBusy(true);
    setError("");
    setLetter("");
    setReachability(null);
    onReachability(null, { documented: false, unknown: false });
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
      })
      .finally(() => { if (!controller.signal.aborted) setSummaryBusy(false); });
    const id = new URLSearchParams(location.search).get("stop");
    if (id) void select(id);
    return () => controller.abort();
  }, []);
  return (
    <section className="gap-study" aria-label="Accessibility gaps">
      <h2>Which stops are harder to reach by wheelchair?</h2>
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
      {summaryBusy && <p role="status"><span className="spinner" /> Loading the sampled stop study…</p>}
      {busy && (
        <p role="status">
          <span className="spinner" /> Computing network reach…
        </p>
      )}
      <h3>Biggest differences in the sample</h3>
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
      <h2>Where is accessibility information missing near a stop?</h2>
      <p>
        See which nearby paths have documented accessibility information and which depend on conditions nobody has recorded. Available for stops in the Diridon pilot area. Results come from map records, not in-person checks.
      </p>
      <label htmlFor="reachability-stop">Stop</label>
      <select id="reachability-stop" value={pilotStopId} onChange={(e) => { setPilotStopId(e.target.value); setReachability(null); onReachability(null, { documented: false, unknown: false }); }}>
        {pilotStops.map((stop) => <option key={stop.stop_id} value={stop.stop_id}>{stop.stop_name} · {stop.stop_id}</option>)}
      </select>
      <label htmlFor="reachability-profile">How do you travel?</label>
      <select id="reachability-profile" value={reachProfile} onChange={(e) => { setReachProfile(e.target.value); setReachability(null); onReachability(null, { documented: false, unknown: false }); }}>
        <option value="wheelchair">Wheelchair</option>
        <option value="stroller">Stroller</option>
        <option value="low_vision">Low vision</option>
        <option value="standard">Walking</option>
      </select>
      <label htmlFor="reachability-minutes">Walking time</label>
      <select id="reachability-minutes" value={reachMinutes} onChange={(e) => { setReachMinutes(Number(e.target.value)); setReachability(null); onReachability(null, { documented: false, unknown: false }); }}>
        <option value={5}>5 minutes</option>
        <option value={10}>10 minutes</option>
        <option value={15}>15 minutes</option>
      </select>
      <button className="button" disabled={!pilotStopId || reachBusy} onClick={() => void analyzeReachability()}>
        {reachBusy ? "Analyzing the pilot network…" : "Show documented and unknown paths"}
      </button>
      {reachError && <p role="alert">{reachError}</p>}
      {reachBusy && <p role="status"><span className="spinner" /> Measuring paths toward this stop…</p>}
      {reachability && reachability.status !== "STOP_CONNECTION_UNKNOWN" && (
        <article className="study-detail" aria-live="polite">
          <h3>{reachability.stop.stop_name}</h3>
          <p>{reachability.status === "NO_SAMPLED_ORIGINS" ? "No origin nodes were available in this bounded sample." : reachability.status === "INSUFFICIENT_DOCUMENTED_DATA" ? "No sampled origins meet this model’s documentation requirements." : "Source-documented reach is available in this sample."}</p>
          <dl>
            <div><dt>Documented origins</dt><dd>{reachability.documented.reachable_sample_origins} / {reachability.sampling.origin_sample_count}</dd></div>
            <div><dt>Possible origins</dt><dd>{reachability.possible.reachable_sample_origins} / {reachability.sampling.origin_sample_count}</dd></div>
            <div><dt>Origins depending on unknowns</dt><dd>{reachability.unknown_gap.sample_origin_count}</dd></div>
          </dl>
          <p>{reachability.profile_assumptions.time_budget_minutes} minute model at {(reachability.profile_assumptions.speed_mps * 2.23694).toFixed(1)} mph. Sample: {reachability.sampling.method.toLowerCase()}.</p>
          <div className="scenario-toggles" aria-label="Map overlays">
            <label><input type="checkbox" checked={showDocumented} disabled={reachability.documented.reachable_edge_count === 0} onChange={(e) => updateLayers(e.target.checked, showUnknown)} /> Documented routes ({reachability.documented.reachable_edge_count} segments)</label>
            <label><input type="checkbox" checked={showUnknown} disabled={reachability.unknown_gap.edge_count === 0} onChange={(e) => updateLayers(showDocumented, e.target.checked)} /> Routes that depend on unknown conditions ({reachability.unknown_gap.edge_count} segments)</label>
          </div>
          {reachability.unknown_gap.examples.length > 0 && <div><h4>Source records with missing conditions</h4><ul>{reachability.unknown_gap.examples.slice(0, 3).map((item) => <li key={`${item.osm_way_id}-${item.source_url}`}><a href={item.source_url} target="_blank" rel="noreferrer">OpenStreetMap way {item.osm_way_id}</a>: missing {item.missing_critical_attributes.join(", ")}</li>)}</ul></div>}
          <section aria-label="Inspection reachability impact">
            <h4>Where another inspection would help most</h4>
            <p>These scores count sampled journeys that change if one unknown connection is blocked. Other unknown conditions remain usable in both scenarios. They do not measure ridership or official priority.</p>
            <p>{reachability.inspection_priorities.evaluated_candidate_count} candidates evaluated from {reachability.inspection_priorities.candidate_count_on_sample_paths} connections on sampled paths; limited to {reachability.inspection_priorities.candidate_limit} candidates.</p>
            <ol>{reachability.inspection_priorities.candidates.slice(0, 5).map(candidate => <li key={candidate.candidate_id}>
              <a href={candidate.source_url} target="_blank" rel="noreferrer">OpenStreetMap way {candidate.source_url.split("/").pop()}</a>: {candidate.score === null ? "impact unavailable" : `${candidate.score} of ${candidate.sample_count} sampled journeys change`}. Missing {candidate.missing_critical_attributes.join(", ")}.
              <details><summary>Calculation details</summary><p>{candidate.assumptions}</p><p>{reachability.inspection_priorities.parallel_edge_policy}</p><p>Changed origin/stop pairs: {candidate.affected_pairs.map(pair => pair.join(" → ")).join("; ") || "none"}.</p></details>
            </li>)}</ol>
            {reachability.inspection_priorities.candidates.length === 0 && <p>No source-linked unknown connections occur on the sampled possible paths.</p>}
          </section>
          {reachability.example_paths.length > 0 && <div><h4>Example paths in the sample</h4><ul>{reachability.example_paths.map((path) => <li key={path.origin_node}>Sample origin node {path.origin_node} · {(path.time_seconds / 60).toFixed(1)} minutes to this stop · {path.source_refs.slice(0, 2).map((ref) => <a key={ref.osm_way_id} href={ref.url} target="_blank" rel="noreferrer"> OSM way {ref.osm_way_id}</a>)}</li>)}</ul></div>}
          <p>OSM source snapshot date: {reachability.osm_source.source_snapshot_date || "not recorded"}; cache file modified: {reachability.osm_source.cache_file_modified_at || "unknown"}; manifest generated: {reachability.osm_source.manifest_generated_at || "unknown"}. Field observation time: none recorded. VTA feed version: {reachability.gtfs_source.feed_info[0]?.feed_version || "not recorded"}.</p>
          {reachability.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </article>
      )}
      {reachability?.status === "STOP_CONNECTION_UNKNOWN" && <p role="status">{reachability.message}</p>}

    </section>
  );
}
