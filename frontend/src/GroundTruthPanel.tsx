import { useEffect, useState, type FormEvent } from "react";
import OriginSearch from "./OriginSearch";
import type { GapFeature, Observation, SourceStatus } from "./types";

import { API, serviceJSON } from "./data";
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
};
const emptyPolygons: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
const categories = [
  ["pedestrian_pothole", "Pothole on a pedestrian path"],
  ["broken_pavement", "Broken pavement"],
  ["blocked_curb_ramp", "Blocked curb ramp"],
  ["construction_obstruction", "Construction obstruction"],
  ["missing_tactile_paving", "Missing tactile paving, observed in person"],
  ["curb_ramp_present", "Curb ramp present"],
  ["curb_ramp_appears_absent", "Curb ramp appears absent"],
  ["stairs", "Stairs"],
  ["sidewalk_obstruction", "Sidewalk obstruction"],
  ["uneven_surface", "Uneven surface"],
  ["sidewalk_condition_issue", "Sidewalk condition issue"],
  ["crossing_issue", "Crossing issue"],
  ["other", "Other"],
];

export default function GroundTruthPanel({
  onFeatures,
  onClearReportPoint,
  onRequestLocation,
  reportPoint,
  onFocusCandidate,
  selectedCandidateId,
  focusReport = 0,
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
      serviceJSON(`${API}/health`).then(data => setReportsEnabled(data.reports_enabled === true))
        .catch(() => { setReportsEnabled(null); setReportAvailabilityError(true); }),
    ]);
  }

  useEffect(() => {
    onFeatures(evidenceData(gaps, reports), showSidewalks ? sidewalks : emptyPolygons);
  }, [gaps, reports, showSidewalks, sidewalks, onFeatures]);

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
    try {
      const response = await fetch(`${API}/accessibility/observations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latitude: Number(latitude),
          longitude: Number(longitude),
          category,
          description,
        }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === "string" ? error.detail : "Report could not be saved. Check the location and try again.");
      }
      setLatitude("");
      setLongitude("");
      setDescription("");
      onClearReportPoint();
      setMessage("Report saved as unverified community evidence.");
      void refresh();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Report could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="groundtruth-panel" aria-label="Accessibility evidence">
      <div className="groundtruth-heading">
        <div>
          <h3>Sidewalk data gaps</h3>
          <p>
            These are places where records disagree or leave questions. They are
            suggestions for review, not confirmed barriers. Countywide routes
            use OSM walking paths; City sidewalk comparisons currently cover the
            Diridon pilot area.
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
      {reportsEnabled ? (
        <>
        <OriginSearch onChoose={([lat,lon]) => { setLatitude(String(lat)); setLongitude(String(lon)); }} />
        <form className="report-form" onSubmit={(event) => void submit(event)}>
          <div>
            <h3 id="report-title" tabIndex={-1}>Report an issue</h3>
            <p>
              R marks where the observation happened. Reports stay unverified
              until someone checks them.
            </p>
          </div>
          <button
            className="evidence-toggle"
            type="button"
            onClick={onRequestLocation}
          >
            {reportPoint ? "Move report pin on map" : "Place report pin on map"}
          </button>
          {reportPoint && (
            <p className="report-point-selected" role="status">
              Report location: {latitude}, {longitude}
            </p>
          )}
          <div className="report-coordinates">
            <label>
              Latitude
              <input
                required
                type="number"
                step="any"
                min="-90"
                max="90"
                value={latitude}
                onChange={(event) => setLatitude(event.target.value)}
              />
            </label>
            <label>
              Longitude
              <input
                required
                type="number"
                step="any"
                min="-180"
                max="180"
                value={longitude}
                onChange={(event) => setLongitude(event.target.value)}
              />
            </label>
          </div>
          <label htmlFor="report-observation">Observation</label>
            <select
              id="report-observation"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              {categories.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          <label>
            Details <span className="optional-label">optional</span>
            <textarea
              maxLength={500}
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe what you observed. Avoid personal details."
            />
          </label>
          <button
            className="button button-primary report-submit"
            disabled={busy || !latitude || !longitude}
            type="submit"
          >
            {busy ? "Saving…" : <>Submit report</>}
          </button>
        </form>
        </>
      ) : (
        <p>
          {reportsEnabled === false ? "Public reporting is paused until durable storage is connected. No report will be saved here." : reportAvailabilityError ? "Reporting availability could not be checked. No report can be submitted until the service responds." : "Checking report availability…"}
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
