import { useEffect, useRef, useState } from "react";
import ReadAloud from "./ReadAloud";
import StopService from "./StopService";
import {
  PROFILES,
  formatDistance,
  formatDuration,
  profileLabel,
  spokenDistance,
  type Place,
} from "./format";
import type { Maneuver, RouteResult as Route } from "./types";

export type Comparison = {
  standard: Route;
  alternative: Route | null;
  extra_distance_m: number | null;
  extra_minutes: number | null;
  unavailable_reason?: string;
  same_mapped_route?: boolean;
  explanation?: string;
};

type Props = {
  route: Route;
  place: Place;
  profile: string;
  updating: boolean;
  onProfile: (profile: string) => void;
  onEdit: () => void;
  onNewTrip: () => void;
  onShare: () => void;
  onFocusStep: (location: [number, number]) => void;
  comparison: Comparison | null;
  comparing: boolean;
  onCompare: () => void;
};

function percent(share: number | null) {
  if (share == null) return "";
  if (share >= 0.995) return "the whole route";
  if (share < 0.01) return "under 1% of the route";
  return `${Math.round(share * 100)}% of the route`;
}

function stepText(step: Maneuver, index: number) {
  const distance = step.distance_m > 0 ? `, ${spokenDistance(step.distance_m)}` : "";
  const extra = step.maneuver === "connector"
    ? (step.notes || []).map((note) => `No walking-path data: ${note}`)
    : [...step.warnings.map((w) => `Possible issue in map data: ${w}`), ...(step.notes || [])];
  return `Step ${index + 1}. ${step.instruction}${distance}. ${extra.join(" ")}`.trim();
}

export default function RouteResult({
  route,
  place,
  profile,
  updating,
  onProfile,
  onEdit,
  onNewTrip,
  onShare,
  onFocusStep,
  comparison,
  comparing,
  onCompare,
}: Props) {
  const summary = route.accessibility_summary;
  const steps = route.directions || [];
  const [directionsOpen, setDirectionsOpen] = useState(
    () => !window.matchMedia("(max-width: 760px)").matches,
  );
  const [fullscreen, setFullscreen] = useState(false);
  const fullscreenHeading = useRef<HTMLHeadingElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    // Start the results at their summary, not at the planner's scroll offset.
    titleRef.current?.closest(".panel-scroll")?.scrollTo({ top: 0 });
    titleRef.current?.focus({ preventScroll: true });
  }, [route]);
  useEffect(() => {
    if (!fullscreen) return;
    fullscreenHeading.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  const destinationName = place.name;
  const arrival = route.arrival?.type === "entrance" ? route.arrival.name : null;
  const summaryText = `Route to ${destinationName}. ${spokenDistance(route.distance_m)}, about ${formatDuration(route.duration_seconds)}, for ${profileLabel(route.profile)}.`;
  const limitations = summary?.lines.length ? summary.lines : [summary?.headline || route.accessibility_warning];
  const directionsList = (
    <ol className="directions">
      {steps.map((step, index) => {
        const concern = (step.documented_concerns || []).length > 0;
        return (
          <li key={index} className={`direction ${concern ? "has-concern" : ""} ${step.maneuver === "connector" ? "is-connector" : ""}`}>
            <button
              type="button"
              className="direction-main"
              onClick={() => step.location && onFocusStep([step.location[1], step.location[0]])}
            >
              <span className="direction-text">{step.instruction}</span>
              {step.distance_m > 0 && <span className="direction-distance">{formatDistance(step.distance_m)}</span>}
            </button>
            {step.maneuver === "connector" ? (
              <p className="direction-note"><strong>No walking-path data: </strong>{step.notes?.[0]}</p>
            ) : (
              <>
                {step.warnings.map((warning) => (
                  <p key={warning} className="direction-note direction-concern"><strong>Possible issue in map data: </strong>{warning}</p>
                ))}
                {(step.notes || []).map((note) => (
                  <p key={note} className="direction-note">{note}</p>
                ))}
              </>
            )}
          </li>
        );
      })}
    </ol>
  );

  return (
    <section className={`route-result ${updating ? "is-updating" : ""}`} aria-labelledby="route-title" aria-busy={updating}>
      <h2 id="route-title" ref={titleRef} tabIndex={-1}>
        To {destinationName}
      </h2>
      <p className="route-headline" hidden={updating}>
        <strong>{formatDistance(route.distance_m)}</strong>
        <span aria-hidden="true"> · </span>
        <strong>{formatDuration(route.duration_seconds)}</strong>
        <span aria-hidden="true"> · </span>
        <span>{profileLabel(route.profile)}</span>
      </p>
      {arrival && !updating && <p className="route-arrival">Ends at the station entrance: {arrival}.</p>}

      <div className="profile-switch" role="radiogroup" aria-label="How do you travel?">
        {PROFILES.map((option) => (
          <label key={option.value}>
            <input
              type="radio"
              name="result-profile"
              value={option.value}
              checked={profile === option.value}
              onChange={() => onProfile(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
      {updating && <p role="status" className="field-hint"><span className="spinner" aria-hidden="true" /> Updating the route for {profileLabel(profile)}…</p>}
      {!updating && <>

      <div className="route-limitations">
        {limitations.map((line) => (
          <p key={line}>{line}</p>
        ))}
        {route.profile_explanation && <p>{route.profile_explanation}</p>}
      </div>

      <div className="route-actions">
        <button
          type="button"
          className="button button-primary"
          aria-expanded={directionsOpen}
          aria-controls="route-directions"
          onClick={() => {
            if (window.matchMedia("(max-width: 760px)").matches) setFullscreen(true);
            else setDirectionsOpen((value) => !value);
          }}
        >
          {directionsOpen ? "Hide directions" : `Show ${steps.length} directions`}
        </button>
        <button type="button" className="button" onClick={onEdit}>
          Edit trip
        </button>
      </div>

      <div id="route-directions" className="directions-inline" hidden={!directionsOpen}>
        {directionsList}
      </div>

      {fullscreen && (
        <div className="directions-fullscreen" role="dialog" aria-modal="true" aria-labelledby="full-directions-title">
          <div className="directions-fullscreen-header">
            <h2 id="full-directions-title" ref={fullscreenHeading} tabIndex={-1}>
              Directions to {destinationName}
            </h2>
            <button type="button" className="button" onClick={() => setFullscreen(false)}>
              Back to map
            </button>
          </div>
          <p className="route-headline">
            {formatDistance(route.distance_m)} · {formatDuration(route.duration_seconds)} · {profileLabel(route.profile)}
          </p>
          {directionsList}
        </div>
      )}

      <ReadAloud
        resetKey={`${route.profile}-${route.distance_m}`}
        label="Read directions aloud"
        text={() => [summaryText, limitations.join(" "), ...steps.map((step, index) => stepText(step, index))].join(" ")}
        sections={[
          { label: "Route summary", text: () => `${summaryText} ${limitations.join(" ")}` },
          { label: "Directions", text: () => steps.map((step, index) => stepText(step, index)).join(" ") },
          {
            label: "More detail",
            text: () =>
              [
                ...(summary?.documented_restrictions || []).map((item) => item.text),
                ...(summary?.missing_information || []).map((item) => `${item.label}: not recorded for ${percent(item.share)}.`),
              ].join(" "),
          },
        ]}
      />

      <details className="plain-details">
        <summary>More detail</summary>
        <h3>Possible issues recorded in the map data</h3>
        {summary?.documented_restrictions.length ? (
          <ul>
            {summary.documented_restrictions.map((item) => (
              <li key={item.code}>
                {item.text} Step{item.steps.length > 1 ? "s" : ""} {item.steps.join(", ")}.
              </li>
            ))}
          </ul>
        ) : (
          <p>No known concerns are recorded for this route. That doesn't confirm the route is usable; some information may be missing.</p>
        )}
        <h3>Missing information</h3>
        {summary?.missing_information.length ? (
          <ul>
            {summary.missing_information.map((item) => (
              <li key={item.attribute}>
                {item.label[0].toUpperCase() + item.label.slice(1)}: not recorded for {percent(item.share)}.
              </li>
            ))}
          </ul>
        ) : (
          <p>The map records each attribute this profile checks.</p>
        )}
        {summary && summary.crossings.total > 0 && (
          <>
            <h3>Street crossings</h3>
            <p>
              {summary.crossings.total} crossing{summary.crossings.total === 1 ? "" : "s"}
              {summary.crossings.unmarked ? `; ${summary.crossings.unmarked} with no marked crosswalk recorded` : ""}
              {summary.crossings.unrecorded_type ? `; ${summary.crossings.unrecorded_type} with no crossing type recorded` : ""}.{" "}
              {route.accessibility
                ? `Curb ramp information is recorded at ${route.accessibility.crossing_observations.known_kerb_information} of ${route.accessibility.crossing_observations.denominator}.`
                : ""}
            </p>
          </>
        )}
        {summary && summary.unmapped_connectors.length > 0 && (
          <>
            <h3>Parts with no walking-path data</h3>
            <ul>
              {summary.unmapped_connectors.map((item) => (
                <li key={item.segment}>
                  {item.position === "start" ? "Near your start" : "Near your destination"}: about {formatDistance(item.distance_m)} in a straight line. The map has no walking-path data here, so we can't confirm a usable path.
                </li>
              ))}
            </ul>
          </>
        )}
        <h3>Community reports</h3>
        <p>
          {route.reviewed_report_effects?.length
            ? `${route.reviewed_report_effects.length} reviewed community report${route.reviewed_report_effects.length === 1 ? "" : "s"} affected this route.`
            : "No reviewed community reports affect this route."}
        </p>
        {route.groundtruth_evidence?.message && (
          <>
            <h3>City sidewalk records</h3>
            <p>{route.groundtruth_evidence.message}</p>
          </>
        )}
        {route.arrival?.note && (
          <>
            <h3>Station entrance</h3>
            <p>{route.arrival.note}</p>
          </>
        )}
        <h3>Compared with standard walking</h3>
        {profile === "standard" ? (
          <p>This is the standard walking route.</p>
        ) : comparison ? (
          <p>
            {comparison.alternative
              ? comparison.same_mapped_route
                ? comparison.explanation
                : `This route is ${formatDistance(Math.abs(comparison.extra_distance_m || 0))} ${(comparison.extra_distance_m || 0) >= 0 ? "longer" : "shorter"} than standard walking. ${comparison.explanation || ""} The grey line on the map shows the standard route.`
              : comparison.unavailable_reason}
          </p>
        ) : (
          <button type="button" className="button" onClick={onCompare} disabled={comparing}>
            {comparing ? "Comparing…" : "Compare with standard walking"}
          </button>
        )}
        <p className="fine-print">{summary?.interpretation} Map data comes from OpenStreetMap and has not been checked in person.</p>
        <details className="quiet-details">
          <summary>Map segments behind these directions ({route.segments?.length || 0})</summary>
          <ol className="segment-evidence">
            {(route.segments || []).map((segment, index) => (
              <li key={index}>
                {formatDistance(segment.length_m)} · {segment.name || segment.kind || "path"} · {segment.reasons.join("; ") || "attributes recorded"}
              </li>
            ))}
          </ol>
        </details>
      </details>

      <details className="plain-details">
        <summary>About {destinationName}</summary>
        <StopService stops={place.stops} />
      </details>

      </>}
      <div className="route-footer-actions">
        <button type="button" className="text-button" onClick={onShare}>
          Copy link to this trip
        </button>
        <button type="button" className="text-button" onClick={onNewTrip}>
          Plan a new trip
        </button>
      </div>
    </section>
  );
}
