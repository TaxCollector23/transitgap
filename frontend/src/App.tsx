import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Accessibility,
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  LocateFixed,
  MapPin,
  Navigation,
  Route as RouteIcon,
  Search,
  X,
} from 'lucide-react'
import MapView from './MapView'
import GroundTruthPanel from './GroundTruthPanel'
import type { Coverage, RouteResult, Stop } from './types'

const API = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')
const METERS_PER_MILE = 1609.344
const algorithms = [
  { value: 'dijkstra', label: 'Dijkstra', description: 'Finds the lowest-cost route for your walking preference.' },
  { value: 'bidirectional_dijkstra', label: 'Bidirectional Dijkstra', description: 'Searches from both ends for the same lowest-cost objective.' },
  { value: 'astar', label: 'A*', description: 'Uses distance to the stop to guide the search toward a lowest-cost route.' },
  { value: 'bellman_ford', label: 'Bellman–Ford', description: 'Finds a lowest-cost route by relaxing edges. Usually slower on large networks.' },
  { value: 'breadth_first', label: 'Breadth-first search', description: 'Chooses the fewest network segments. The walking distance may be longer.' },
]
type RouteKey = { origin: [number, number]; stopId: string; algorithm: string; profile: string }

function distanceM(a: [number, number], b: [number, number]) {
  const rad = (value: number) => (value * Math.PI) / 180
  const dLat = rad(b[0] - a[0])
  const dLon = rad(b[1] - a[1])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon / 2) ** 2
  return 6371000 * 2 * Math.asin(Math.sqrt(h))
}

function insideRing(point: [number, number], ring: number[][]) {
  const [latitude, longitude] = point
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    const crosses = (yi > latitude) !== (yj > latitude) && longitude < ((xj - xi) * (latitude - yi)) / (yj - yi) + xi
    if (crosses) inside = !inside
  }
  return inside
}

function insideCoverage(point: [number, number], coverage: Coverage) {
  if (!coverage.boundary) return distanceM([coverage.center.latitude, coverage.center.longitude], point) <= coverage.radius_m
  const polygons = coverage.boundary.type === 'Polygon' ? [coverage.boundary.coordinates] : coverage.boundary.coordinates
  return polygons.some((polygon) => insideRing(point, polygon[0]) && !polygon.slice(1).some((ring) => insideRing(point, ring)))
}

function messageForUser(message: string) {
  return message
    .replace(/\b(\d+(?:\.\d+)?)\s*(?:kilometers?|kilometres?|km)\b/g, (_, value: string) => `${(Number(value) / 1.609344).toFixed(2)} mi`)
    .replace(/\b(\d+(?:\.\d+)?)\s*(?:meters?|metres?|m)\b/g, (_, value: string) => `${(Number(value) / METERS_PER_MILE).toFixed(2)} mi`)
}

function detailOf(data: unknown) {
  const detail = (data as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return messageForUser(detail)
  if (detail && typeof detail === 'object') {
    const fields = detail as { message?: string; initialization_error?: string }
    return messageForUser(fields.message || fields.initialization_error || 'The request could not be completed.')
  }
  return 'The request could not be completed.'
}

function readError(error: unknown) {
  return error instanceof Error ? messageForUser(error.message) : 'Something went wrong. Try again.'
}

export default function App() {
  const [coverage, setCoverage] = useState<Coverage | null>(null)
  const [stops, setStops] = useState<Stop[]>([])
  const [origin, setOrigin] = useState<[number, number] | null>(null)
  const [destination, setDestination] = useState<Stop | null>(null)
  const [algorithm, setAlgorithm] = useState('dijkstra')
  const [profile, setProfile] = useState('standard')
  const [result, setResult] = useState<RouteResult | null>(null)
  const [resultKey, setResultKey] = useState<RouteKey | null>(null)
  const [loading, setLoading] = useState(true)
  const [mapReady, setMapReady] = useState(false)
  const [dataReady, setDataReady] = useState(false)
  const [calculating, setCalculating] = useState(false)
  const [mapMode, setMapMode] = useState<'idle' | 'origin' | 'report'>('idle')
  const selecting = mapMode !== 'idle'
  const reportPlacement = mapMode === 'report'
  const [searchText, setSearchText] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [panelExpanded, setPanelExpanded] = useState(true)
  const [evidenceFeatures, setEvidenceFeatures] = useState<GeoJSON.FeatureCollection<GeoJSON.Point>>({ type: 'FeatureCollection', features: [] })
  const [sidewalkFeatures, setSidewalkFeatures] = useState<GeoJSON.FeatureCollection>({ type: 'FeatureCollection', features: [] })
  const [reportPoint, setReportPoint] = useState<[number, number] | null>(null)
  const [candidateFocus, setCandidateFocus] = useState<[number, number] | null>(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const dataLoadRef = useRef<Promise<void> | null>(null)
  const requestRef = useRef<AbortController | null>(null)
  const inFlightRef = useRef(false)

  const loadData = useCallback(() => {
    if (dataLoadRef.current) return dataLoadRef.current
    setLoading(true)
    setError('')
    const request = (async () => {
      try {
        const [healthResponse, coverageResponse, stopsResponse] = await Promise.all([
          fetch(`${API}/health`),
          fetch(`${API}/coverage`),
          fetch(`${API}/stops`),
        ])
        const health = await healthResponse.json()
        if (!healthResponse.ok || !health.ready) throw new Error(health.error || 'Transit and walking data could not be loaded.')
        if (!coverageResponse.ok) throw new Error(detailOf(await coverageResponse.json().catch(() => null)))
        if (!stopsResponse.ok) throw new Error(detailOf(await stopsResponse.json().catch(() => null)))
        const nextCoverage = (await coverageResponse.json()) as Coverage
        const stopData = (await stopsResponse.json()) as { stops: Stop[] }
        setCoverage(nextCoverage)
        setStops(stopData.stops)
        setDataReady(true)
        setStatus(`${stopData.stops.length} VTA stops loaded for ${nextCoverage.region || 'the study area'}`)
      } catch (nextError) {
        setDataReady(false)
        setError(nextError instanceof TypeError
          ? 'TransitGap could not reach the transit and walking data service. Check your connection, then try again.'
          : readError(nextError))
        setStatus('Map is available. Route data needs attention.')
      } finally {
        setLoading(false)
        dataLoadRef.current = null
      }
    })()
    dataLoadRef.current = request
    return request
  }, [])

  useEffect(() => {
    void loadData()
    return () => requestRef.current?.abort()
  }, [loadData])

  const currentKey = useMemo<RouteKey | null>(() => {
    if (!origin || !destination) return null
    return { origin, stopId: destination.stop_id, algorithm, profile }
  }, [origin, destination, algorithm, profile])
  const resultIsStale = Boolean(result && (!resultKey || !currentKey ||
    resultKey.stopId !== currentKey.stopId || resultKey.algorithm !== currentKey.algorithm ||
    resultKey.profile !== currentKey.profile || resultKey.origin[0] !== currentKey.origin[0] ||
    resultKey.origin[1] !== currentKey.origin[1]
  ))
  const canRoute = dataReady && Boolean(origin && destination) && !calculating

  const nearbyStops = useMemo(() => {
    const query = searchText.trim().toLocaleLowerCase()
    const center: [number, number] = origin || [coverage?.center.latitude ?? 37.3296, coverage?.center.longitude ?? -121.903]
    return stops
      .filter((stop) => !query || stop.stop_name.toLocaleLowerCase().includes(query))
      .map((stop) => ({ stop, distance: distanceM(center, [stop.latitude, stop.longitude]) }))
      .sort((a, b) => a.distance - b.distance || a.stop.stop_name.localeCompare(b.stop.stop_name))
      .slice(0, query ? 8 : 4)
  }, [coverage, origin, searchText, stops])

  const cancelRouteRequest = () => {
    requestRef.current?.abort()
    requestRef.current = null
    inFlightRef.current = false
    setCalculating(false)
  }

  const setStart = (point: [number, number]) => {
    if (coverage && !insideCoverage(point, coverage)) {
      setError(`That point is outside the supported ${coverage.region || 'study'} area. Choose a point inside the dotted map boundary.`)
      setStatus('Starting point was not changed')
      setPanelExpanded(true)
      return
    }
    cancelRouteRequest()
    setOrigin(point)
    setMapMode('idle')
    setPanelExpanded(true)
    setError('')
    setStatus('Starting point selected')
  }

  const chooseOnMap = () => {
    setMapMode('origin')
    setPanelExpanded(false)
    setError('')
    setStatus('Choose a point inside the dotted map boundary. Press Escape to cancel.')
  }

  const cancelMapSelection = useCallback(() => {
    setMapMode('idle')
    setPanelExpanded(true)
    setStatus('Map selection cancelled')
  }, [])

  useEffect(() => {
    if (mapMode === 'idle') return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        cancelMapSelection()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [mapMode, cancelMapSelection])

  const useMyLocation = () => {
    setError('')
    if (!navigator.geolocation) {
      setError('Location is not available in this browser. Choose a point on the map instead.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => setStart([position.coords.latitude, position.coords.longitude]),
      (geoError) => setError(geoError.code === 1
        ? 'Location access was denied. Choose a point on the map instead.'
        : geoError.code === 2
          ? 'Your location could not be found. Choose a point on the map instead.'
          : 'The location request timed out. Try again or choose a point on the map.'),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
    )
  }

  const chooseStop = (stop: Stop) => {
    cancelRouteRequest()
    setDestination(stop)
    setMapMode('idle')
    setPanelExpanded(true)
    setSearchText('')
    setSearchOpen(false)
    setError('')
    setStatus(`Destination selected: ${stop.stop_name}`)
  }

  const clearStart = () => {
    cancelRouteRequest()
    setOrigin(null)
    setMapMode('idle')
    setError('')
    setStatus('Choose a new starting point')
  }

  const calculate = async () => {
    if (!origin || !destination || !dataReady || inFlightRef.current) return
    const key: RouteKey = { origin, stopId: destination.stop_id, algorithm, profile }
    const controller = new AbortController()
    requestRef.current = controller
    inFlightRef.current = true
    setCalculating(true)
    setError('')
    try {
      const response = await fetch(`${API}/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          origin_latitude: origin[0],
          origin_longitude: origin[1],
          destination_stop_id: destination.stop_id,
          algorithm,
          profile,
        }),
        signal: controller.signal,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(detailOf(data))
      if (controller.signal.aborted) return
      setResult(data as RouteResult)
      setResultKey(key)
      setStatus('Route calculated on the mapped walking network')
      setPanelExpanded(true)
    } catch (nextError) {
      if (!controller.signal.aborted) {
        setError(nextError instanceof TypeError
          ? 'TransitGap could not reach the routing service. Check your connection and try again.'
          : readError(nextError))
        setStatus('Route could not be calculated')
      }
    } finally {
      if (requestRef.current === controller) requestRef.current = null
      inFlightRef.current = false
      setCalculating(false)
    }
  }

  const reset = () => {
    cancelRouteRequest()
    setOrigin(null)
    setDestination(null)
    setSearchText('')
    setSearchOpen(false)
    setMapMode('idle')
    setResult(null)
    setResultKey(null)
    setError('')
    setStatus(dataReady ? `${stops.length} VTA stops loaded for ${coverage?.region || 'the study area'}` : 'Route data unavailable')
    setPanelExpanded(true)
  }

  const routeFeature = result && !resultIsStale ? {
    type: 'Feature' as const,
    properties: {},
    geometry: result.geometry,
  } : null

  const handleMapOrigin = useCallback((point: [number, number]) => {
    if (reportPlacement) {
      setReportPoint(point)
      setMapMode('idle')
      setPanelExpanded(true)
      setStatus('Report location selected')
      return
    }
    setStart(point)
  }, [reportPlacement, setStart])

  return (
    <main className={`app-shell ${panelExpanded ? '' : 'sheet-is-collapsed'}`}>
      <section className="map-shell" aria-label="Map">
        <MapView
          coverage={coverage}
          stops={stops}
          origin={origin}
          destination={destination}
          route={routeFeature}
          selecting={selecting}
          panelExpanded={panelExpanded}
          onReady={() => setMapReady(true)}
          onOrigin={handleMapOrigin}
          onStop={chooseStop}
          evidence={evidenceFeatures}
          sidewalks={sidewalkFeatures}
          focusPoint={candidateFocus}
          onCandidate={(id) => { setSelectedCandidateId(id); setPanelExpanded(true) }}
          reportPoint={reportPoint}
        />
        <div className="map-badge" aria-hidden="true"><span className="map-badge-dot" /> {coverage?.region?.toUpperCase() || 'TRANSITGAP MAP'} <span>·</span> VTA</div>
        <div className="map-legend" aria-label="Map key"><strong>Map key</strong><span><i className="map-key-a">A</i> Your start</span><span><i className="map-key-b">B</i> VTA stop</span><span><i className="map-key-route" /> Walking route</span><span><i className="map-key-gap" /> Data to review</span><span><i className="map-key-report" /> Unverified report</span><span><i className="map-key-city" /> City sidewalk record</span></div>
        {selecting && <div className="map-selection-banner" role="status"><span>{reportPlacement ? 'R · Tap the map to place your report location' : 'A · Tap inside the boundary to set your start'}</span><button type="button" onClick={cancelMapSelection}>Cancel <span className="sr-only">map selection</span></button></div>}
        {(!mapReady || loading) && <div className="map-loading" role="status"><span className="spinner" /><span>{!mapReady ? 'Preparing map…' : 'Loading transit and walking data…'}</span></div>}
      </section>

      <aside className={`panel ${panelExpanded ? 'panel-expanded' : 'panel-collapsed'}`} aria-label="Route planner">
        <div className="panel-scroll">
          <header className="panel-header">
            <a className="brand-lockup" href="/" aria-label="TransitGap home">
              <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
              <div><div className="eyebrow">{coverage?.region?.toUpperCase() || 'WALKING ACCESS TO TRANSIT'}</div><h1>TransitGap</h1></div>
            </a>
            <button className="mobile-panel-toggle icon-button" onClick={() => setPanelExpanded((expanded) => !expanded)} aria-label={panelExpanded ? 'Collapse route planner' : 'Expand route planner'} aria-expanded={panelExpanded}>
              {panelExpanded ? <ChevronDown size={19} /> : <ChevronUp size={19} />}
            </button>
          </header>

          <div className="panel-content">
            <div className="panel-title-row">
              <div><p className="panel-kicker">WALKING DIRECTIONS</p><h2>Plan a walk</h2></div>
              <span className={`dataset-status ${dataReady ? 'is-ready' : ''}`} role="status"><span />{loading ? 'Loading' : dataReady ? `${stops.length} stops` : 'Unavailable'}</span>
            </div>

            {error && <div className="notice error" role="alert"><CircleHelp size={17} /><span>{error}</span>{!dataReady && !loading && <button className="text-button" onClick={() => void loadData()}>Try again</button>}</div>}

            <section className="step-section" aria-labelledby="origin-title">
              <div className="step-heading"><span className={`step-number ${origin ? 'step-done' : ''}`}>{origin ? '✓' : 'A'}</span><div><h3 id="origin-title">Choose your start</h3><p>Any point inside the dotted study boundary.</p></div></div>
              <div className={`selection-card ${origin ? 'selection-card-set' : ''}`}>
                <div className="selection-icon start-icon"><MapPin size={16} /></div>
                <div className="selection-content"><span className="selection-label">{origin ? 'START SELECTED' : 'YOUR START'}</span><strong>{origin ? `${origin[0].toFixed(5)}, ${origin[1].toFixed(5)}` : 'Choose where to start'}</strong></div>
                {origin && <button className="icon-button change-button" onClick={clearStart} aria-label="Change starting point"><X size={16} /></button>}
              </div>
              <div className="origin-actions">
                {mapMode === 'origin' ? (
                  <button className="button button-secondary" onClick={cancelMapSelection}><X size={16} /> Cancel choosing start</button>
                ) : (
                  <button className={`button button-secondary ${selecting ? 'button-active' : ''}`} onClick={chooseOnMap}><MapPin size={16} /> Choose on map</button>
                )}
                <button className="button button-secondary" onClick={useMyLocation}><LocateFixed size={16} /> Use my location</button>
              </div>
            </section>

            <section className="step-section destination-section" aria-labelledby="destination-title">
              <div className="step-heading"><span className={`step-number ${destination ? 'step-done' : ''}`}>{destination ? '✓' : 'B'}</span><div><h3 id="destination-title">Choose a VTA stop</h3><p>Pick a real stop from search or tap a green stop on the map.</p></div></div>
              {destination && (
                <div className="selected-stop" aria-live="polite">
                  <span className="destination-pin">B</span><div className="selected-stop-copy"><span>DESTINATION</span><strong>{destination.stop_name}</strong></div>
                  <button className="change-stop" onClick={() => { setDestination(null); setSearchOpen(true); requestAnimationFrame(() => searchRef.current?.focus()) }}>Change</button>
                </div>
              )}
              <label className="search-box" htmlFor="stop-search"><Search size={17} aria-hidden="true" /><input
                ref={searchRef}
                id="stop-search"
                type="search"
                aria-label="Search VTA stops"
                value={searchText}
                placeholder={destination ? 'Search to change destination' : 'Find a VTA stop by name'}
                autoComplete="off"
                onFocus={() => setSearchOpen(true)}
                onChange={(event) => { setSearchText(event.target.value); setSearchOpen(true) }}
                aria-controls="stop-results"
                aria-expanded={searchOpen}
              />{searchText && <button className="search-clear icon-button" onClick={() => { setSearchText(''); setSearchOpen(true); searchRef.current?.focus() }} aria-label="Clear stop search"><X size={15} /></button>}</label>
              {searchOpen && (
                <div className="stop-results" id="stop-results" role="region" aria-label="VTA stop results">
                  <div className="results-caption">{searchText ? 'MATCHING VTA STOPS' : origin ? 'NEAR YOUR START · STRAIGHT-LINE DISTANCE' : 'VTA STOPS NEAR DIRIDON'}</div>
                  {!loading && nearbyStops.length === 0 && <p className="no-stops">No stops match “{searchText}”. Try another name.</p>}
                  {nearbyStops.map(({ stop, distance }) => <button
                    className={`stop-option ${destination?.stop_id === stop.stop_id ? 'stop-option-selected' : ''}`}
                    key={stop.stop_id}
                    type="button"
                    aria-pressed={destination?.stop_id === stop.stop_id}
                    onClick={() => chooseStop(stop)}
                  ><span className="stop-option-pin"><MapPin size={15} /></span><span className="stop-option-copy"><strong>{stop.stop_name}</strong><small>{(distance / METERS_PER_MILE).toFixed(2)} mi straight-line</small></span><ArrowUpRight size={15} className="stop-option-arrow" /></button>)}
                  <div className="results-footnote">Straight-line distance only. Walking distance appears after routing.</div>
                </div>
              )}
            </section>

            <section className="step-section profile-section" aria-labelledby="profile-title">
              <div className="step-heading step-heading-compact"><span className="step-number step-number-muted"><Accessibility size={15} /></span><div><h3 id="profile-title">Walking preference</h3><p>Choose which path network to consider.</p></div></div>
              <div className="profile-options" role="group" aria-label="Route profile">
                <button type="button" className={`profile-option ${profile === 'standard' ? 'profile-option-active' : ''}`} aria-pressed={profile === 'standard'} onClick={() => setProfile('standard')}><span className="radio-dot" /><span><strong>Shortest route</strong><small>Use mapped walking paths</small></span></button>
                <button type="button" className={`profile-option ${profile === 'avoid_mapped_stairs' ? 'profile-option-active' : ''}`} aria-pressed={profile === 'avoid_mapped_stairs'} onClick={() => setProfile('avoid_mapped_stairs')}><span className="radio-dot" /><span><strong>Avoid mapped stairs</strong><small>Skips stairs tagged in OpenStreetMap</small></span></button>
                <button type="button" className={`profile-option ${profile === 'prefer_documented_paths' ? 'profile-option-active' : ''}`} aria-pressed={profile === 'prefer_documented_paths'} onClick={() => setProfile('prefer_documented_paths')}><span className="radio-dot" /><span><strong>Prefer documented paths</strong><small>Favors segments with more relevant map tags</small></span></button>
              </div>
              <p className="accessibility-note">More map detail is not a guarantee of accessibility. Missing tags are unknown.</p>
            </section>

            <details className="advanced-settings">
              <summary><span>Advanced settings</span><span className="advanced-summary-value">{algorithms.find((item) => item.value === algorithm)?.label}<ChevronDown size={15} /></span></summary>
              <label htmlFor="algorithm">Routing algorithm</label>
              <select id="algorithm" value={algorithm} onChange={(event) => setAlgorithm(event.target.value)}>{algorithms.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select>
              <p className="algorithm-help">{algorithms.find((item) => item.value === algorithm)?.description}</p>
              <p>All options use the same mapped walking network.</p>
            </details>

            <div className="route-actions">
              <button className="button button-primary find-route" onClick={() => void calculate()} disabled={!canRoute} aria-busy={calculating}>
                {calculating ? <><span className="spinner light" /> Finding route…</> : <><RouteIcon size={18} /> Find Route <ArrowDownRight size={16} className="find-arrow" /></>}
              </button>
              {result && <button className="button button-reset" onClick={reset}>Reset</button>}
            </div>
            {!origin && <p className="form-hint">Choose a start and a VTA stop to find your route.</p>}

            {result && (
              <section className={`route-result ${resultIsStale ? 'route-result-stale' : ''}`} aria-live="polite" aria-label="Route details">
                <div className="route-result-header"><div><span className="result-kicker">{resultIsStale ? 'ROUTE NEEDS AN UPDATE' : 'ROUTE FOUND'}</span><h3>{result.destination.stop_name}</h3></div><span className="route-result-icon"><Navigation size={17} /></span></div>
                {resultIsStale && <p className="stale-message">Your start, stop or settings changed. Find the route again to update the map.</p>}
                <div className="route-metrics"><div><strong>{(result.distance_m / METERS_PER_MILE).toFixed(2)} <small>mi</small></strong><span>walking distance</span></div><div><strong>{Math.max(1, Math.round(result.duration_seconds / 60))} <small>min</small></strong><span>at {(result.walking_speed_mps_assumed * 2.23694).toFixed(1)} mph assumed</span></div></div>
                <div className="route-facts"><span>{algorithms.find((item) => item.value === result.algorithm)?.label}</span><span>{result.graph_nodes_traversed} network nodes</span><span>{result.mapped_stair_segments} mapped stair segments</span></div>
                {result.algorithm_warning && <p className="algorithm-help">{result.algorithm_warning}</p>}
                {result.accessibility && <details className="route-data-details">
                  <summary>What the map documents</summary>
                  <p>OpenStreetMap tags are not field verified. Missing information is unknown, not proof of access.</p>
                  {result.optimization_objective && <p>Objective: {result.optimization_objective}.</p>}
                  <dl>
                    <div><dt>Surface tags</dt><dd>{(result.accessibility.surface_distance_known_m / METERS_PER_MILE).toFixed(2)} mi recorded · {(result.accessibility.surface_distance_missing_m / METERS_PER_MILE).toFixed(2)} mi missing</dd></div>
                    <div><dt>Crossings with kerb tags</dt><dd>{result.accessibility.crossing_observations.known_kerb_information} of {result.accessibility.crossing_observations.denominator}</dd></div>
                    <div><dt>Tagged barrier observations</dt><dd>{result.accessibility.known_mapped_barrier_count}</dd></div>
                    {result.optimization_cost_m !== undefined && <div><dt>Optimization cost</dt><dd>{result.optimization_cost_m.toFixed(1)} cost-meters; not walking distance</dd></div>}
                  </dl>
                  {result.accessibility.missing_attributes.length > 0 && <p className="missing-tags">Relevant tags missing on mapped segments: {result.accessibility.missing_attributes.map((item) => `${item.attribute} (${item.observations})`).join(', ')}.</p>}
                  <p>{result.accessibility.interpretation}</p>
                </details>}
                {result.groundtruth_evidence && <details className="route-data-details"><summary>Accessibility information along this route</summary><p>{result.groundtruth_evidence.message}</p>{result.groundtruth_evidence.features.length > 0 && <><p>{result.groundtruth_evidence.nearby_feature_count} City sidewalk polygons are within 15 m of the route. Proximity does not confirm that the route uses those sidewalks.</p><dl>{result.groundtruth_evidence.features.slice(0, 5).map((feature) => <div key={feature.source_feature_id}><dt>City feature {feature.source_feature_id}</dt><dd>{feature.distance_to_route_m} m away · ADA record: {feature.ada_compliance_record || 'unknown'} · source update: {feature.last_update || 'unknown'}</dd></div>)}</dl></>}</details>}
                <div className="route-warning"><Accessibility size={16} /><p>{result.accessibility_warning}</p></div>
              </section>
            )}

            <GroundTruthPanel onFeatures={(gaps, sidewalks) => { setEvidenceFeatures(gaps); setSidewalkFeatures(sidewalks) }} onClearReportPoint={() => setReportPoint(null)} onRequestLocation={() => { setMapMode('report'); setPanelExpanded(false); setStatus('Tap the map to place your report pin. Press Escape to cancel.') }} reportPoint={reportPoint} onFocusCandidate={(point) => { setCandidateFocus(point); setSelectedCandidateId(null) }} selectedCandidateId={selectedCandidateId} />

            <footer className="panel-footer"><span>OpenStreetMap · VTA GTFS</span><span className="footer-status"><span />{dataReady ? 'Data ready' : status || 'Starting'}</span></footer>
          </div>
        </div>
      </aside>
      <div className="sr-only" role="status" aria-live="polite">{status}</div>
    </main>
  )
}
