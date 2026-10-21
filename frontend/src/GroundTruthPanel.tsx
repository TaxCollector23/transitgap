import { useEffect, useRef, useState, type FormEvent } from "react";
import OriginSearch from "./OriginSearch";
import type { GapFeature, Observation, SourceStatus } from "./types";

import { API, serviceJSON, warmRouting } from "./data";
const METERS_PER_MILE = 1609.344;
type Props = {
  onFeatures: (
    gaps: GeoJSON.FeatureCollection<GeoJSON.Point>,
    sidewalks: GeoJSON.FeatureCollection,
  ) => void;
  onClearReportPoint: () => void;
  onRequestLocation: () => void;
  reportPoint: [number, number] | null;
  onFocusCandidate: (point: [number, number]) => void;
  selectedCandidateId: string | null;
  focusReport?: number;
  mode?: "evidence" | "report";
  onReport?: () => void;
};
const emptyPolygons: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
const categories = [
  ["pedestrian_pothole", "Pothole affecting pedestrians"],
  ["broken_pavement", "Broken sidewalk"],
  ["blocked_curb_ramp", "Blocked curb ramp"],
  ["construction_obstruction", "Construction obstruction"],
  ["missing_tactile_paving", "Missing tactile paving, observed in person"],
  ["curb_ramp_present", "Curb ramp present"],
  ["curb_ramp_appears_absent", "Missing curb ramp"],
  ["stairs", "Stairs"],
  ["sidewalk_obstruction", "Sidewalk obstruction"],
  ["uneven_surface", "Uneven pavement"],
  ["sidewalk_condition_issue", "Sidewalk condition issue"],
  ["crossing_issue", "Blocked crossing"],
  ["other", "Other accessibility concern"],
];

export default function GroundTruthPanel({
  onFeatures,
  onClearReportPoint,
  onRequestLocation,
  reportPoint,
  onFocusCandidate,
  selectedCandidateId,
  focusReport = 0,
  mode = "evidence",
  onReport,
}: Props) {
  const [gaps, setGaps] = useState<GapFeature[]>([]);
  const [reports, setReports] = useState<Observation[]>([]);
  const [sources, setSources] = useState<SourceStatus | null>(null);
  const [evidenceState, setEvidenceState] = useState<
    "loading" | "ready" | "unavailable"
  >("loading");
  const [sidewalks, setSidewalks] =
    useState<GeoJSON.FeatureCollection>(emptyPolygons);
  const [showSidewalks, setShowSidewalks] = useState(false);
  const [selected, setSelected] = useState<GapFeature | null>(null);
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [category, setCategory] = useState("sidewalk_condition_issue");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [reportsEnabled, setReportsEnabled] = useState<boolean | null>(null);
  const [reportsState, setReportsState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [sourcesUnavailable, setSourcesUnavailable] = useState(false);
  const [reportAvailabilityError, setReportAvailabilityError] = useState(false);
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState("");
  const submission = useRef<{body:string; key:string} | null>(null);

  function evidenceData(
    items: GapFeature[],
    community: Observation[],
  ): GeoJSON.FeatureCollection<GeoJSON.Point> {
    return {
      type: "FeatureCollection",
      features: [
        ...items.map((item) => ({
          type: "Feature" as const,
          id: item.id,
          properties: { id: item.id, classification: item.classification },
          geometry: {
            type: "Point" as const,
            coordinates: [item.longitude, item.latitude] as [number, number],
          },
        })),
        ...community.map((item) => ({
          type: "Feature" as const,
          id: item.id,
          properties: { id: item.id, classification: "COMMUNITY_REPORTED" },
          geometry: {
            type: "Point" as const,
            coordinates: [item.longitude, item.latitude] as [number, number],
          },
        })),
      ],
    };
  }

  async function refresh() {
    setEvidenceState("loading");
    setReportsState("loading");
    setSourcesUnavailable(false);
    setReportAvailabilityError(false);
    // Source metadata and community/health requests must not hold back the
    // independently available source-linked candidate records.
    await Promise.allSettled([
      serviceJSON(`${API}/data-sources`).then(data => setSources(data as SourceStatus))
        .catch(() => setSourcesUnavailable(true)),
      serviceJSON(`${API}/accessibility/priorities?limit=80`).then(data => {
        setGaps(data.candidates as GapFeature[]);
        setEvidenceState("ready");
      }).catch(error => {
        setEvidenceState("unavailable");
        setMessage(error instanceof Error ? error.message : "Accessibility evidence unavailable.");
      }),
      serviceJSON(`${API}/accessibility/observations?limit=100`).then(data => {
        setReports(data.observations as Observation[]);
        setReportsState("ready");
      }).catch(() => setReportsState("unavailable")),
      serviceJSON(`${API}/health`).then(async data => {
        if (!data.ready && !data.error) {
          if (!await warmRouting()) throw Error("Service is still starting");
          data = await serviceJSON(`${API}/health`);
        }
        setReportsEnabled(data.reports_enabled === true);
      })
        .catch(() => { setReportsEnabled(null); setReportAvailabilityError(true); }),
    ]);
  }

  useEffect(() => {
    onFeatures(evidenceData(mode === "report" ? [] : gaps, reports), showSidewalks ? sidewalks : emptyPolygons);
  }, [gaps, reports, showSidewalks, sidewalks, onFeatures, mode]);

  useEffect(() => {
    void refresh().catch((error: unknown) =>
      setMessage(
        error instanceof Error ? error.message : "Evidence unavailable.",
      ),
    );
  }, []);
  useEffect(() => {
    if (focusReport) document.getElementById("report-title")?.focus();
  }, [focusReport, reportsEnabled]);
  useEffect(() => {
    if (reportPoint) {
      setLatitude(String(reportPoint[0].toFixed(6)));
      setLongitude(String(reportPoint[1].toFixed(6)));
    }
  }, [reportPoint]);
  useEffect(() => {
    if (!selectedCandidateId) return;
    const candidate = gaps.find((item) => item.id === selectedCandidateId);
    if (candidate) setSelected(candidate);
  }, [selectedCandidateId, gaps]);

  async function toggleSidewalks() {
    if (!showSidewalks && sidewalks.features.length === 0) {
      try {
        const response = await fetch(
          `${API}/accessibility/municipal-sidewalks?limit=1000`,
        );
        if (!response.ok)
          throw new Error("City sidewalk polygons are unavailable.");
        const payload = (await response.json()) as GeoJSON.FeatureCollection;
        setSidewalks(payload);
        setShowSidewalks(true);
        onFeatures(evidenceData(gaps, reports), payload);
      } catch (error) {
        setMessage(
          error instanceof Error
            ? error.message
            : "City sidewalk polygons are unavailable.",
        );
      }
      return;
    }
    const next = !showSidewalks;
    setShowSidewalks(next);
    onFeatures(evidenceData(gaps, reports), next ? sidewalks : emptyPolygons);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setSaved("");
    try {
      const body = JSON.stringify({latitude:Number(latitude),longitude:Number(longitude),category,description,
        website:new FormData(event.currentTarget as HTMLFormElement).get("website") || ""});
      if (submission.current?.body !== body) submission.current = {body,key:crypto.randomUUID()};
      const response = await fetch(`${API}/accessibility/observations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key":submission.current.key },
        body,
        signal:AbortSignal.timeout(15000),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === "string" ? error.detail : "Report could not be saved. Check the location and try again.");
      }
      const confirmation = await response.json();
      if (!confirmation.id || confirmation.review_status !== "UNVERIFIED")
        throw Error("The service did not confirm your saved report. Please try again.");
      setLatitude("");
      setLongitude("");
      setDescription("");
      onClearReportPoint();
      setSaved("Report saved as unverified community evidence.");
      submission.current = null;
      void refresh();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Report could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  const locationText = latitude && longitude ? `${Number(latitude).toFixed(5)}, ${Number(longitude).toFixed(5)}` : "";
  if (mode === "report")
    return (
      <section className="groundtruth-panel report-panel" aria-labelledby="report-title">
        <h2 id="report-title" tabIndex={-1}>Report an issue</h2>
        <p>Tell others about a sidewalk or crossing problem. Reports are shown as unverified until someone reviews them. Please don't include personal details.</p>
        {reportsEnabled === false ? (
          <p role="status" className="notice">Public reporting is paused until durable storage is connected. No report will be saved here.</p>
        ) : reportsEnabled === null ? (
          <p role="status">{reportAvailabilityError ? "Reporting availability could not be checked. No report can be submitted until the service responds." : "Checking report availability…"}</p>
        ) : (
          <>
            <section className="report-step" aria-labelledby="report-where">
              <h3 id="report-where">1. Where is the problem?</h3>
              {locationText ? (
                <div className="field-value">
                  <span className="field-value-text"><strong>{reportPoint ? "Point chosen on the map" : "Chosen location"}</strong><span>{locationText}</span></span>
                  <button type="button" className="text-button field-change" onClick={() => { setLatitude(""); setLongitude(""); onClearReportPoint(); }}>Change<span className="sr-only"> report location</span></button>
                </div>
              ) : (
                <>
                  <div className="origin-actions">
                    <button type="button" className="button" onClick={() => {
                      if (!navigator.geolocation) { setMessage("Location is not available in this browser. Choose on the map or search an address."); return; }
                      navigator.geolocation.getCurrentPosition(
                        (position) => { setLatitude(String(position.coords.latitude)); setLongitude(String(position.coords.longitude)); },
                        () => setMessage("Your location couldn't be used. Choose on the map or search an address."),
                        { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
                      );
                    }}>Use my location</button>
                    <button type="button" className="button" onClick={onRequestLocation}>Choose on map</button>
                  </div>
                  <OriginSearch label="Address or place of the problem" onChoose={([lat, lon]) => { setLatitude(String(lat)); setLongitude(String(lon)); }} />
                </>
              )}
            </section>
            <form className="report-form" onSubmit={(event) => void submit(event)}>
              <div hidden aria-hidden="true"><label>Website<input name="website" tabIndex={-1} autoComplete="off" /></label></div>
              <label htmlFor="report-observation"><span className="report-step-title">2. What's the problem?</span></label>
              <select id="report-observation" value={category} onChange={(event) => setCategory(event.target.value)}>
                {categories.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <label htmlFor="report-details"><span className="report-step-title">3. Details</span> (optional)</label>
              <textarea id="report-details" maxLength={500} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What did you see? For example: the curb ramp is blocked by a pole." />
              <button className="button button-primary report-submit" disabled={busy || !latitude || !longitude} aria-describedby="report-submit-hint" type="submit">
                {busy ? "Saving…" : "Submit report"}
              </button>
              {(!latitude || !longitude) && <p className="field-hint" id="report-submit-hint">Choose where the problem is (step 1) to submit.</p>}
            </form>
          </>
        )}
        {message && <p className="notice error" role="alert">{message}</p>}
        {saved && <p className="notice success" role="status">{saved}</p>}
      </section>
    );
  return (
    <section className="groundtruth-panel" aria-label="Accessibility evidence">
      <div className="groundtruth-heading">
        <div>
          <h2>Sidewalk records that need review</h2>
          <p>
            Places where map and city records disagree or leave questions. These
            are suggestions for an in-person check, not confirmed barriers. City
            sidewalk records currently cover the Diridon area only.
          </p>
        </div>
        <button
          className="evidence-toggle"
          type="button"
          onClick={() => void toggleSidewalks()}
          aria-pressed={showSidewalks}
        >
          {showSidewalks ? "Hide city sidewalks" : "Show city sidewalks"}
        </button>
      </div>
      {message && (
        <p className="evidence-message" role="status">
          {message}
        </p>
      )}
      {sourcesUnavailable && <p role="status">Source metadata is unavailable. Candidate records still include their individual source details.</p>}
      {evidenceState === "loading" && (
        <p className="evidence-message" role="status">
          <span className="spinner" />
          Loading sidewalk evidence…
        </p>
      )}
      {(evidenceState === "unavailable" || sourcesUnavailable || reportsState === "unavailable" || reportAvailabilityError) && (
        <button
          className="text-button"
          type="button"
          onClick={() => {
            setMessage("");
            void refresh().catch((error: unknown) =>
              setMessage(
                error instanceof Error
                  ? error.message
                  : "Evidence unavailable.",
              ),
            );
          }}
        >
          Try loading evidence again
        </button>
      )}
      <details className="plain-details">
        <summary>Source availability</summary>
        <ul>
          {sources?.sources.map((source) => (
            <li key={source.id}>
              {source.name}: {source.status};{" "}
              {source.feature_count ?? "unknown"} records
              {source.coverage_radius_m
                ? ` within ${(source.coverage_radius_m / METERS_PER_MILE).toFixed(2)} mi near Diridon`
                : ""}
            </li>
          ))}
        </ul>
      </details>
      <p className="evidence-definitions">
        <strong>Data to review:</strong> map records suggest a possible gap.{" "}
        <strong>City sidewalk:</strong> a municipal record, not a field check.{" "}
        <strong>Community report:</strong> shared by a person and not yet
        verified.
      </p>
      <div className="evidence-legend">
        <span>
          <i className="legend-gap" />
          Evidence candidate
        </span>
        <span>
          <i className="legend-report" />
          Unverified report
        </span>
        <span>
          <i className="legend-city" />
          City sidewalk record
        </span>
      </div>
      <p>These comparison scores use proximity to sampled routes. For computed journey reachability changes, use the stop study in Access gaps.</p>
      <div className="gap-list" aria-label="Route-proximity review suggestions">
        {gaps.slice(0, 12).map((gap) => (
          <button
            key={gap.id}
            type="button"
            className={`gap-item ${selected?.id === gap.id ? "gap-item-selected" : ""}`}
            onClick={() => {
              setSelected(gap);
              onFocusCandidate([gap.latitude, gap.longitude]);
            }}
          >
            <span className="gap-score">
              {gap.priority_score === null
                ? "—"
                : Math.round(gap.priority_score)}
            </span>
            <span className="gap-copy">
              <strong>
                {gap.classification.replace(/_/g, " ").toLowerCase()}
              </strong>
            </span>
          </button>
        ))}
        {gaps.length === 0 && (
          <p className="evidence-empty">
            {message
              ? "Evidence could not be loaded. Try again after the service is available."
              : evidenceState === "loading" ? "Loading review candidates…" : "No review candidates are available for this area right now."}
          </p>
        )}
      </div>
      {selected && (
        <article className="gap-detail">
          <div className="gap-detail-title">
            <strong>Evidence detail</strong>
            <button
              type="button"
              onClick={() => setSelected(null)}
              aria-label="Close evidence detail"
            >
              ×
            </button>
          </div>
          <p>{selected.explanation}</p>
          <p>{selected.provenance.interpretation}</p>
          <dl>
            <div>
              <dt>Municipal source</dt>
              <dd>
                {selected.provenance.municipal_source?.status ||
                  "No matching record"}
              </dd>
            </div>
            <div>
              <dt>OpenStreetMap</dt>
              <dd>
                {selected.provenance.osm_source?.status || "No matching record"}
              </dd>
            </div>
            <div>
              <dt>Nearest source distance</dt>
              <dd>
                {selected.matched_distance_m == null
                  ? "Not matched"
                  : `${(selected.matched_distance_m / METERS_PER_MILE).toFixed(2)} mi`}
              </dd>
            </div>
            <div>
              <dt>Route-proximity score</dt>
              <dd>
                {selected.priority_score == null
                  ? "Unavailable"
                  : `${selected.priority_score}/100 · inspection suggestion only`}
              </dd>
            </div>
          </dl>
        </article>
      )}
      {mode === "evidence" && onReport && (
        <p>
          Noticed a problem on a sidewalk or crossing?{" "}
          <button type="button" className="text-button" onClick={onReport}>Report an issue</button>
        </p>
      )}
      <div className="community-reports">
        <h4>
          Community reports{" "}
          {reportsState === "ready" && <span>{reports.length}</span>}
        </h4>
        {reportsState === "loading" ? (
          <p role="status">Loading community reports…</p>
        ) : reportsState === "unavailable" ? (
          <p>Community reports are unavailable. Their count is unknown.</p>
        ) : (
          <>
            {reports.slice(0, 5).map((report) => (
              <article key={report.id}>
                <strong>{report.category.replace(/_/g, " ")}</strong>
                <p>
                  {report.review_status === "REVIEWED" ? "Reviewed community report" : report.review_status === "UNDER_REVIEW" ? "Under review" : "Unverified"} ·{" "}
                  {new Date(report.created_at).toLocaleDateString()}
                </p>
                {report.description && <p>{report.description}</p>}
                <details><summary>Report details</summary><p>Report ID: {report.id}</p><p>Source: community observation. Last updated: {new Date(report.updated_at || report.created_at).toLocaleString()}.</p><a href={`${API}/accessibility/observations/${report.id}`} target="_blank" rel="noreferrer">Open report and review history</a></details>
              </article>
            ))}
            {reports.length === 0 && <p>No reports yet.</p>}
          </>
        )}
      </div>
    </section>
  );
}
