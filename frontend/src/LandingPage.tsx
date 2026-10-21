import { useEffect } from "react";
import "./landing.css";
import ReadAloud from "./ReadAloud";
import { PREPARED, warmRouting } from "./data";

const steps = [
  ["Find your stop", "Choose where you're starting and select a nearby VTA stop. TransitGap uses real geographic and transit data to explore the available walking routes."],
  ["Explore your options", "Compare available routes and see how different mobility needs can affect the journey. Look beyond distance to understand the obstacles and limitations recorded along the way."],
  ["Understand the details", "See which accessibility details are documented, where information is missing, and which locations may need a closer look."],
];

export default function LandingPage() {
  useEffect(() => {
    document.body.classList.add("landing-page");
    if (PREPARED) void warmRouting();
    return () => document.body.classList.remove("landing-page");
  }, []);
  return (
    <main className="landing">
      <a className="landing-skip" href="#why-transitgap">Skip introduction</a>
      <section className="landing-hero" aria-labelledby="landing-title">
        <img className="landing-art" src="/images/city-for-all.webp" alt="" fetchPriority="high" width="1672" height="941" />
        <div className="landing-sky" />
        <header className="landing-nav">
          <a className="landing-brand" href="/">TransitGap</a>
          <nav aria-label="Main navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#methodology">Data &amp; methods</a>
            <a href="/app">Open the map</a>
          </nav>
        </header>
        <div className="landing-copy">
          <h1 id="landing-title">A city for all.</h1>
          <p>A bus stop can be close and still hard to reach. TransitGap helps you find walking routes, identify accessibility barriers, and understand what's missing from the map.</p>
          <div className="landing-actions">
            <a className="landing-primary" href="/app">Explore the map</a>
            <a className="landing-secondary" href="#how-it-works">How TransitGap works</a>
          </div>
        </div>
      </section>
      <div className="landing-editorial">
        <ReadAloud text={() => Array.from(document.querySelectorAll<HTMLElement>(".landing-copy h1,.landing-copy > p,.landing-editorial section h2,.landing-editorial section h3,.landing-editorial section p")).filter(e=>e.getClientRects().length && !e.closest('[hidden],[inert],[aria-hidden="true"]')).map(e=>e.innerText).join(". ")} />
        <section className="landing-split" id="why-transitgap">
          <h2>A nearby stop isn't always an easy stop to reach.</h2>
          <div>
            <p>A bus stop might be only a few blocks away, but the route to get there can make all the difference. Stairs, difficult crossings, uneven surfaces, and missing information can turn a short walk into a much more complicated journey.</p>
            <p>TransitGap looks beyond the distance between two points. It helps people understand the routes leading to public transit and the information available about them.</p>
          </div>
        </section>
        <section id="how-it-works" className="landing-how">
          <div className="landing-section-intro">
            <h2>Find a route that works for you.</h2>
            <p>TransitGap brings walking routes, transit stops, and accessibility information together in one place.</p>
          </div>
          <ol className="landing-steps">
            {steps.map(([title, body], i) => <li key={title}><span aria-hidden="true">0{i + 1}</span><h3>{title}</h3><p>{body}</p></li>)}
          </ol>
        </section>
        <section className="landing-split">
          <h2>What the map doesn't know matters too.</h2>
          <div>
            <p>Not every sidewalk, curb ramp, or crossing has complete accessibility information. When those details are missing, an ordinary map may not tell the whole story.</p>
            <p>TransitGap makes these gaps visible. Instead of treating unknown conditions as confirmed accessible paths, it shows what has been documented and what still needs to be checked.</p>
          </div>
        </section>
        <section className="landing-split">
          <h2>Better information can make a better city.</h2>
          <div>
            <p>TransitGap doesn't just help people explore individual routes. It can also highlight places where accessibility information is incomplete, helping communities understand which crossings and pathways deserve more attention.</p>
            <p>By bringing together public geographic and transit information, the project aims to make the journey to public transit easier to understand and the information behind it more useful.</p>
          </div>
        </section>
        <section className="landing-split" id="methodology">
          <h2>Built on information you can examine.</h2>
          <div>
            <p>TransitGap uses public geographic and transit information to understand the paths connecting people to transit stops. Each source has its own strengths and limitations, which is why knowing where information comes from matters.</p>
            <p><a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> supplies the walking network. <a href="https://www.vta.org/go/developers">VTA</a>, <a href="https://www.caltrain.com/developer-resources">Caltrain</a>, and <a href="https://www.bart.gov/schedules/developers/gtfs">BART</a> publish the transit stop and schedule data. <a href="https://geo.sanjoseca.gov/server/rest/services/OPN/OPN_OpenDataService/MapServer/185">San José municipal GIS</a> adds curb-ramp evidence in the Diridon pilot area.</p>
            <p>Routes are based on recorded data, not field verification. <a href="https://github.com/TaxCollector23/transitgap/blob/main/docs/METHODOLOGY.md">Read the methods and limitations.</a></p>
          </div>
        </section>
        <section className="landing-final">
          <h2>See your city a little differently.</h2>
          <p>Explore routes to public transit, discover what accessibility information is available, and see where the map still has questions.</p>
          <a className="landing-primary" href="/app">Open TransitGap</a>
        </section>
        <footer className="landing-footer">
          <a className="landing-brand" href="/">TransitGap</a>
          <nav aria-label="Footer navigation">
            <a href="/app">Open the map</a>
            <a href="#methodology">Data &amp; methods</a>
            <a href="https://github.com/TaxCollector23/transitgap">GitHub</a>
            <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>
            <a href="https://www.vta.org/go/developers">VTA data</a>
            <a href="https://www.caltrain.com/developer-resources">Caltrain data</a>
            <a href="https://www.bart.gov/schedules/developers/gtfs">BART data</a>
          </nav>
        </footer>
      </div>
    </main>
  );
}
