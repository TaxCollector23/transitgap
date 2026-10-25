import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import OriginSearch from "./OriginSearch";
import type { GapFeature, Observation, SourceStatus, Stop } from "./types";

import { API, serviceJSON } from "./data";
import { distanceM, formatDistance } from "./format";
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
  stops?: Stop[];
  onReviewSummary?: (summary: ReviewSummary) => void;
};
export type ReviewSummary =
  | { state: "loading" }
  | { state: "unavailable" }
  | { state: "ready"; candidates: number; stopsWithin150m: number; stopsWithin50m: number };
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

function candidateCheck(gap: GapFeature) {
  const hasCity = Boolean(gap.provenance.municipal_source);
  const hasOsm = Boolean(gap.provenance.osm_source);
  const missingLabels: Record<string, string> = {
    width: "sidewalk width", "sidewalk width": "sidewalk width", surface: "surface", smoothness: "surface condition", wheelchair: "wheelchair access",
    incline: "slope", kerb: "curb ramp details", crossing: "crossing details", "tactile paving": "tactile paving",
  };
  const missing = [...new Set(gap.missing_information.map((item) => {
    const field = item.toLowerCase().replace(/^(osm|municipal)\s+/, "").replace(/\s+tag$/, "").replace(/_/g, " ");
    return missingLabels[field] || "another walking detail";
  }))];
  const missingText = missing.length
    ? `Not recorded on the map: ${missing.join(", ")}. Check in person.`
    : "";
  if (hasCity && hasOsm) {
    const sourceText = gap.classification === "CONFLICTING_SOURCES"
      ? "Check whether the City sidewalk record and the mapped path describe the same path; compare the sidewalk details in person."
      : "Check whether the nearby City sidewalk record and mapped path describe the same path, and confirm where each one connects.";
    return [sourceText, missingText].filter(Boolean).join(" ");
  }
  if (hasCity)
    return ["Check whether the City sidewalk record connects to a walking path shown on the map. The records do not line up closely, which does not prove that a path is missing.", missingText].filter(Boolean).join(" ");
  return missingText || "Available records do not give enough detail about this location. Compare the map with the sidewalk in person.";
}

function candidateExplanation(gap: GapFeature) {
  return `${candidateCheck(gap)} These are inspection suggestions, not confirmed barriers.`;
}

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
  stops = [],
  onReviewSummary,
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
  const [reportAvailabilityError, setReportAvailabilityError] = useState<"starting" | "unavailable" | null>(null);
  const [checkingReports, setCheckingReports] = useState(false);
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState("");
  const submission = useRef<{body:string; key:string} | null>(null);

  const candidateLocations = useMemo(() => new Map<string, { stop_name: string; distance_m: number } | null>(
    gaps.map((gap) => {
      const listed = gap.nearby_stops?.[0];
      if (listed) return [gap.id, listed];
      const nearest = stops.reduce<{ stop_name: string; distance_m: number } | null>((best, stop) => {
        const distance = distanceM([gap.latitude, gap.longitude], [stop.latitude, stop.longitude]);
        return !best || distance < best.distance_m ? { stop_name: stop.stop_name, distance_m: distance } : best;
      }, null);
      return [gap.id, nearest];
    }),
  ), [gaps, stops]);

  useEffect(() => {
    if (!onReviewSummary) return;
    if (evidenceState === "loading" || evidenceState === "unavailable") {
      onReviewSummary({ state: evidenceState });
      return;
    }
    const stopsWithin150m = new Set<string>();
    const stopsWithin50m = new Set<string>();
    for (const gap of gaps.slice(0, 80)) {
      for (const stop of stops) {
        const distance = distanceM([gap.latitude, gap.longitude], [stop.latitude, stop.longitude]);
        if (distance <= 150) {
          stopsWithin150m.add(stop.stop_id);
          if (distance <= 50) stopsWithin50m.add(stop.stop_id);
        }
      }
    }
    onReviewSummary({
      state: "ready",
      candidates: Math.min(gaps.length, 80),
      stopsWithin150m: stopsWithin150m.size,
      stopsWithin50m: stopsWithin50m.size,
    });
  }, [evidenceState, gaps, onReviewSummary, stops]);

  async function checkReportAvailability() {
    setReportAvailabilityError(null);
    setCheckingReports(true);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch(`${API}/health`, { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error("Report service is unavailable.");
      const health = await response.json();
      if (health.ready !== true) {
        setReportsEnabled(null);
        setReportAvailabilityError("starting");
      } else if (health.reports_enabled === true) setReportsEnabled(true);
      else setReportsEnabled(false);
    } catch {
      setReportsEnabled(null);
      setReportAvailabilityError("unavailable");
    } finally {
      window.clearTimeout(timeout);
      setCheckingReports(false);
    }
  }

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
    // Reporting only needs a health check. Loading the evidence index here
    // starts unrelated, expensive requests on a cold serverless worker and can
    // leave a stale routing error beside the report form.
    if (mode === "report") {
      await checkReportAvailability();
      return;
    }
    setEvidenceState("loading");
    setReportsState("loading");
    setSourcesUnavailable(false);
    setReportAvailabilityError(null);
    async function loadPriorities() {
      const first = await serviceJSON(`${API}/accessibility/priorities?limit=80`);
      const firstCandidates = first.candidates as GapFeature[];
      setGaps(firstCandidates.slice(0, 80));
      setEvidenceState("ready");
    }
    // Source metadata and community-report requests must not hold back the
    // independently available source-linked candidate records.
    await Promise.allSettled([
      serviceJSON(`${API}/data-sources`).then(data => setSources(data as SourceStatus))
        .catch(() => setSourcesUnavailable(true)),
      loadPriorities().catch(error => {
        setEvidenceState("unavailable");
        setMessage(error instanceof Error ? error.message : "Accessibility evidence unavailable.");
      }),
      serviceJSON(`${API}/accessibility/observations?limit=100`).then(data => {
        setReports(data.observations as Observation[]);
        setReportsState("ready");
      }).catch(() => setReportsState("unavailable")),
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
    if (reportsEnabled !== true) {
      const location = latitude && longitude ? `${Number(latitude).toFixed(6)}, ${Number(longitude).toFixed(6)}` : "Not provided";
      const subject = `TransitGap report: ${categories.find(([value]) => value === category)?.[1] || category}`;
      const body = [
        "I found missing or incorrect accessibility information in TransitGap.",
        "",
        `Problem: ${categories.find(([value]) => value === category)?.[1] || category}`,
        `Location (latitude, longitude): ${location}`,
        `Map: ${window.location.href}`,
        "",
        "Details:",
        description.trim() || "No additional details provided.",
        "",
        "Please do not include personal or sensitive information.",
      ].join("\n");
      const params = new URLSearchParams({ subject, body });
      window.location.href = `mailto:ranganbalaji23@gmail.com?${params.toString()}`;
      setSaved("Your email draft is ready. Review it and press Send in your email app; TransitGap does not send it automatically.");
      return;
    }
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
        {reportsEnabled !== true && (
          <div role="status" className="notice">
            {reportsEnabled === false ? (
              <p>Reports are not saved by this deployment. Use the form to prepare an email to ranganbalaji23@gmail.com.</p>
            ) : reportAvailabilityError ? (
              <>
                {reportAvailabilityError === "starting" ? (
                  <p>TransitGap report storage is unavailable. You can still prepare an email report below.</p>
                ) : (
                  <p>Report storage could not be checked. Use the form to prepare an email to ranganbalaji23@gmail.com.</p>
                )}
                <button type="button" className="text-button" onClick={() => void checkReportAvailability()}>Try checking storage again</button>
              </>
            ) : <p>{checkingReports ? "Checking report storage…" : "Report storage is unavailable. You can prepare an email report below."}</p>}
          </div>
        )}
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
                {busy ? "Saving…" : reportsEnabled === true ? "Submit report" : "Prepare email report"}
              </button>
              {(!latitude || !longitude) && <p className="field-hint" id="report-submit-hint">Choose where the problem is (step 1) to submit.</p>}
            </form>
        </>
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
      <p>The list below points to places where sidewalk records may need a closer look. The separate Access gaps study shows how recorded paths affect a small sample of trips.</p>
      <div className="gap-list" aria-label="Sidewalk review suggestions">
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
            <span className="gap-copy">
              <strong>{candidateLocations.get(gap.id)
                ? `Near ${candidateLocations.get(gap.id)!.stop_name}, ${formatDistance(candidateLocations.get(gap.id)!.distance_m)} — ${candidateCheck(gap)}`
                : `Location detail not listed — ${candidateCheck(gap)}`}</strong>
              <span>Inspection suggestion only; this is not a confirmed barrier.</span>
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
            <strong>What to check</strong>
            <button
              type="button"
              onClick={() => setSelected(null)}
              aria-label="Close review detail"
            >
              ×
            </button>
          </div>
          {candidateLocations.get(selected.id) && <p>Look near {candidateLocations.get(selected.id)!.stop_name}, about {formatDistance(candidateLocations.get(selected.id)!.distance_m)} away.</p>}
          <p>{candidateExplanation(selected)}</p>
          <details className="technical-detail">
            <summary>More detail</summary>
            <p>{selected.priority_score == null
              ? "Review priority score is unavailable."
              : `Review priority score: ${selected.priority_score}/100 — this is a proximity-based review priority, not a measure of barrier severity.`}</p>
            <dl>
              <div><dt>Municipal source status</dt><dd>{selected.provenance.municipal_source?.status || "No matching record"}</dd></div>
              <div><dt>OpenStreetMap source status</dt><dd>{selected.provenance.osm_source?.status || "No matching record"}</dd></div>
              <div><dt>Nearest source match</dt><dd>{selected.matched_distance_m == null ? "Not matched" : `${(selected.matched_distance_m / METERS_PER_MILE).toFixed(2)} mi`}</dd></div>
              <div><dt>Recorded detail fields</dt><dd>{selected.missing_information.length ? selected.missing_information.join(", ") : "No missing field list"}</dd></div>
            </dl>
          </details>
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
