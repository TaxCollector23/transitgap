import { useEffect, useState } from "react";
import "./landing.css";
const API =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "" : "http://localhost:8000");
type Gap = {
  properties: { stop_id: string; stop_name: string; gap_score: number };
};

export default function LandingPage() {
  const [study, setStudy] = useState<{
    features: Gap[];
    evaluated_stop_count: number;
    loaded_stop_count: number;
  } | null>(null);
  const [network, setNetwork] = useState<{
    standard: number[][][];
    wheelchair: number[][][];
  } | null>(null);
  useEffect(() => {
    document.body.classList.add("landing-page");
    const controller = new AbortController();
    fetch(`${API}/gaps?limit=5`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        setStudy(data);
        const id = data.features[0]?.properties.stop_id;
        if (id)
          fetch(`${API}/stops/${encodeURIComponent(id)}/access`, {
            signal: controller.signal,
          })
            .then((r) => (r.ok ? r.json() : null))
            .then((item) => {
              if (item)
                setNetwork({
                  standard: item.standard.geometry.geometries.map(
                    (g: { coordinates: number[][] }) => g.coordinates,
                  ),
                  wheelchair: item.wheelchair.geometry.geometries.map(
                    (g: { coordinates: number[][] }) => g.coordinates,
                  ),
                });
            })
            .catch(() => undefined);
      })
      .catch(() => undefined);
    return () => {
      controller.abort();
      document.body.classList.remove("landing-page");
    };
  }, []);
  const coordinates = network?.standard.flat() || [];
  const xs = coordinates.map((p) => p[0]),
    ys = coordinates.map((p) => p[1]);
  const minX = Math.min(...xs),
    minY = Math.min(...ys),
    width = Math.max(...xs) - minX || 1,
    height = Math.max(...ys) - minY || 1;
  function points(line: number[][]) {
    return line
      .map(
        ([x, y]) =>
          `${30 + ((x - minX) / width) * 460},${370 - ((y - minY) / height) * 340}`,
      )
      .join(" ");
  }
  return (
    <main className="landing">
      <header className="landing-nav">
        <a className="landing-brand" href="/">
          TransitGap
        </a>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#methodology">Data & methods</a>
          <a className="landing-nav-cta" href="/app">
            Open the map ↗
          </a>
        </nav>
      </header>
      <section className="landing-hero">
        <div className="landing-copy">
          <h1>
            The shortest route isn’t always
            <br />
            <em>a usable route.</em>
          </h1>
          <p className="landing-lede">
            A transit stop can be a few blocks away and still be difficult to
            reach. Compare the journey for different mobility needs, see what
            the map knows, and find the places that need a closer look.
          </p>
          <div className="landing-actions">
            <a className="landing-primary" href="/app">
              Explore the map ↗
            </a>
            <a className="landing-secondary" href="/app?view=gaps">
              See access gaps
            </a>
          </div>
        </div>
        <figure
          className="network-preview"
          aria-label="Actual ten-minute pedestrian networks from the stop access study"
        >
          {network ? (
            <>
              <svg
                viewBox="0 0 520 400"
                role="img"
                aria-label="Standard reachable paths in grey and wheelchair-profile paths in green"
              >
                {network.standard.map((line, i) => (
                  <polyline
                    key={`s${i}`}
                    points={points(line)}
                    fill="none"
                    stroke="#acb8ad"
                    strokeWidth="2"
                  />
                ))}
                {network.wheelchair.map((line, i) => (
                  <polyline
                    key={`w${i}`}
                    points={points(line)}
                    fill="none"
                    stroke="#176b5b"
                    strokeWidth="2.5"
                  />
                ))}
              </svg>
              <figcaption>
                {study?.features[0]?.properties.stop_name}
                <br />
                10-minute reach: <span className="standard-key">
                  standard
                </span>{" "}
                / <span className="profile-key">wheelchair model</span>
              </figcaption>
            </>
          ) : (
            <div className="network-loading">
              Actual pedestrian network analysis
              <br />
              <a href="/app?view=gaps">Explore the study →</a>
            </div>
          )}
        </figure>
      </section>
      <section className="landing-editorial" id="how-it-works">
        <h2>
          A bus stop on a map
          <br />
          isn’t a stop everyone can reach.
        </h2>
        <div>
          <p>
            A staircase, a steep path, or an undocumented crossing can change an
            entire trip. TransitGap measures the last part of the journey to
            real VTA stops across Santa Clara County.
          </p>
          <ol className="method-list">
            <li>Choose a start and a transit stop.</li>
            <li>Compare a standard route with your mobility profile.</li>
            <li>Inspect the evidence, then prepare a request for review.</li>
          </ol>
        </div>
      </section>
      <section className="landing-study" id="access-gaps">
        <div>
          <h2>
            Look beyond
            <br />
            one route.
          </h2>
          <p>
            Our ten-minute study follows the pedestrian network toward each
            stop. It compares reachable path length under standard and
            wheelchair assumptions. These are modelled differences, not
            confirmed inaccessible places.
          </p>
          <a href="/app?view=gaps">Explore access gaps →</a>
        </div>
        <div>
          {study && study.features.length > 0 ? (
            <>
              <h3>Largest gaps in the evaluated sample</h3>
              <ol className="study-list">
                {study.features.map(({ properties: p }) => (
                  <li key={p.stop_id}>
                    <a
                      href={`/app?view=gaps&stop=${encodeURIComponent(p.stop_id)}`}
                    >
                      <span>{p.stop_name}</span>
                      <strong>{Math.round(p.gap_score * 100)}%</strong>
                    </a>
                  </li>
                ))}
              </ol>
              <p>
                {study.evaluated_stop_count} stops evaluated out of{" "}
                {study.loaded_stop_count.toLocaleString()} loaded VTA stops.
                Speeds: 2.7 mph standard, 2.0 mph wheelchair. Speed assumptions
                and mapped constraints both affect the results.
              </p>
            </>
          ) : (
            <p>
              The study loads from the same open-data engine as the map.{" "}
              <a href="/app?view=gaps">Open the study</a> to inspect
              availability.
            </p>
          )}
        </div>
      </section>
      <section className="landing-editorial" id="methodology">
        <h2>
          Show the evidence.
          <br />
          Keep the unknowns.
        </h2>
        <div>
          <p>
            An OpenStreetMap tag, a City of San José record, and a community
            observation are different kinds of evidence. None automatically
            means a path has been checked on the ground. Unknown conditions stay
            unknown.
          </p>
          <p>
            Routes use OpenStreetMap and official VTA GTFS. Municipal sidewalk
            comparisons cover the Diridon pilot area. The access study uses a
            spatial sample of county stops, not a ranking of the entire transit
            system.
          </p>
          <p>
            <a href="https://github.com/TaxCollector23/transitgap/blob/main/docs/METHODOLOGY.md">
              Read the methodology →
            </a>
          </p>
        </div>
      </section>
      <section className="landing-faq">
        <h2>Before you travel</h2>
        <details>
          <summary>Is a route verified accessible?</summary>
          <p>
            No. Profiles use mapped constraints and preferences. Surfaces,
            kerbs, slopes and crossings may be missing, inaccurate, or out of
            date. TransitGap has not independently field checked these paths.
          </p>
        </details>
        <details>
          <summary>What does the access gap measure?</summary>
          <p>
            The difference in unique network length reachable toward a stop in
            ten minutes. Standard and wheelchair profiles use different assumed
            speeds and mapped constraints. It is not a population estimate, an
            infrastructure grade, or a measure of disability.
          </p>
        </details>
        <details>
          <summary>How can I help?</summary>
          <p>
            Review the mapped evidence, prepare an editable letter, or
            contribute missing sidewalk and kerb details to{" "}
            <a href="https://wiki.openstreetmap.org/wiki/Sidewalks">
              OpenStreetMap
            </a>
            . Public reporting is paused until durable storage is available. No
            field observations or testimonials have been invented.
          </p>
        </details>
      </section>
      <section className="landing-closing">
        <h2>
          Better access starts
          <br />
          with better information.
        </h2>
        <a className="landing-primary" href="/app">
          Open TransitGap ↗
        </a>
      </section>
      <footer className="landing-footer">
        <a className="landing-brand" href="/">
          TransitGap
        </a>
        <a href="https://www.openstreetmap.org/copyright">
          © OpenStreetMap contributors
        </a>
        <a href="https://www.vta.org/go/developers">VTA GTFS</a>
        <a href="https://github.com/TaxCollector23/transitgap">
          Source code ↗
        </a>
      </footer>
    </main>
  );
}
