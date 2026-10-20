import { ArrowDownRight, ArrowRight, MapPinned, Route, Waypoints } from 'lucide-react'
import { useEffect, useState } from 'react'
import './landing.css'

export default function LandingPage() {
  const [coverageName, setCoverageName] = useState('Current route coverage')
  useEffect(() => {
    const api = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')
    fetch(`${api}/coverage`).then((response) => response.ok ? response.json() : null)
      .then((coverage) => { if (coverage?.region) setCoverageName(coverage.region) })
      .catch(() => undefined)
  }, [])
  return (
    <main className="landing">
      <header className="landing-nav">
        <a className="landing-brand" href="/" aria-label="TransitGap home"><span className="landing-mark"><i /><i /><i /></span>TransitGap</a>
        <nav aria-label="Main navigation"><a href="#how-it-works">How it works</a><a href="#evidence">The evidence</a><a className="landing-nav-cta" href="/app">Open the map <ArrowRight size={15} /></a></nav>
      </header>

      <section className="landing-hero">
        <div className="landing-copy">
          <p className="landing-eyebrow"><span /> WALKING ACCESS TO TRANSIT</p>
          <h1>Can you get to the stop<br /><em>on foot?</em></h1>
          <p className="landing-lede">TransitGap compares walking routes with the sidewalk information that cities and communities have recorded, so missing details are easier to see.</p>
          <div className="landing-actions"><a className="landing-primary" href="/app">Plan a walk <ArrowDownRight size={17} /></a><a className="landing-secondary" href="#how-it-works">See how it works</a></div>
          <p className="landing-coverage"><MapPinned size={15} /> Route study: {coverageName} · City records vary by municipality</p>
        </div>
        <div className="landing-map" aria-label="Illustration of a walking route to transit" role="img">
          <div className="map-street street-a" /><div className="map-street street-b" /><div className="map-street street-c" /><div className="map-block block-a" /><div className="map-block block-b" /><div className="map-block block-c" /><div className="map-block block-d" />
          <svg className="landing-route" viewBox="0 0 520 430" aria-hidden="true"><path d="M74 320 C128 320 116 268 177 268 S220 192 290 192 S345 118 421 118" /><circle cx="74" cy="320" r="8" /><circle cx="421" cy="118" r="8" /></svg>
          <span className="map-point map-start">A <small>START</small></span><span className="map-point map-stop">B <small>VTA STOP</small></span>
          <span className="map-note"><i /> Sidewalk information varies by block</span>
          <div className="map-caption"><span>SANTA CLARA COUNTY</span><span>WALKING NETWORK</span></div>
        </div>
      </section>

      <section className="landing-method" id="how-it-works">
        <div className="section-intro"><span className="landing-eyebrow">A CLEARER WAY TO ASK</span><h2>See the walk.<br />See what’s known.</h2></div>
        <div className="method-steps">
          <article><span className="method-icon"><MapPinned size={18} /></span><p>01 / SET YOUR START</p><h3>Pick a place to begin</h3><span>Choose a point on the map or use your location.</span></article>
          <article><span className="method-icon"><Route size={18} /></span><p>02 / CHOOSE A STOP</p><h3>Find a VTA stop</h3><span>Search by name or select a marked stop.</span></article>
          <article><span className="method-icon"><Waypoints size={18} /></span><p>03 / REVIEW THE RECORDS</p><h3>Notice the unknowns</h3><span>Compare mapped walking paths with available public records.</span></article>
        </div>
      </section>

      <section className="landing-evidence" id="evidence"><div><span className="landing-eyebrow">EVIDENCE, WITH LIMITS</span><h2>Unknown is not the same as inaccessible.</h2></div><p>TransitGap uses OpenStreetMap walking-network tags, VTA stop data, City of San Jose sidewalk records, and community observations. Municipal records do not currently cover every county city. These sources have different verification levels. A route result is not an accessibility certification.</p><a href="/app">Explore the map <ArrowRight size={15} /></a></section>
      <footer className="landing-footer"><a className="landing-brand" href="/">TransitGap</a><span>Open data, visible gaps, better questions.</span><a href="https://github.com/TaxCollector23/transitgap">View the source <ArrowRight size={14} /></a></footer>
    </main>
  )
}
