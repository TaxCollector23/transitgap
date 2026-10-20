import { useCallback, useEffect, useMemo, useState } from 'react'
import MapView from './MapView'
import type { Coverage, RouteResult, Stop } from './types'

const API = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')
const algorithms = [{value:'dijkstra',label:'Dijkstra'},{value:'bidirectional_dijkstra',label:'Bidirectional Dijkstra'},{value:'astar',label:'A*'}]
const profiles = [{value:'standard',label:'Shortest walking route'},{value:'avoid_mapped_stairs',label:'Avoid mapped stairs'}]
function messageOf(error:unknown){ if(error instanceof Error) return error.message; return 'Something went wrong. Please try again.' }
function detailOf(data:any){return typeof data?.detail==='string'?data.detail:data?.detail?.message || data?.detail?.initialization_error || 'Request failed.'}

export default function App(){
  const [coverage,setCoverage]=useState<Coverage|null>(null),[stops,setStops]=useState<Stop[]>([]),[origin,setOrigin]=useState<[number,number]|null>(null),[destination,setDestination]=useState<Stop|null>(null),[algorithm,setAlgorithm]=useState('dijkstra'),[profile,setProfile]=useState('standard'),[result,setResult]=useState<RouteResult|null>(null),[loading,setLoading]=useState(true),[calculating,setCalculating]=useState(false),[selecting,setSelecting]=useState(false),[error,setError]=useState(''),[status,setStatus]=useState('')
  const refresh=useCallback(async()=>{setLoading(true);setError('');try{const [healthRes,covRes,stopRes]=await Promise.all([fetch(API+'/health'),fetch(API+'/coverage'),fetch(API+'/stops')]); const health=await healthRes.json(); if(!healthRes.ok || !health.ready) throw new Error(health.error||'TransitGap data is not ready. Start the backend to load real OSM and VTA data.'); const cov=await covRes.json(); const stopData=await stopRes.json();setCoverage(cov);setStops(stopData.stops);setStatus(stopData.count+' VTA stops loaded')}catch(e){setError(messageOf(e));setStatus('Map can be viewed; route data unavailable')}finally{setLoading(false)}},[])
  useEffect(()=>{void refresh()},[refresh])
  const clear=()=>{setOrigin(null);setDestination(null);setResult(null);setSelecting(false);setError('');setStatus('Selections cleared')}
  const calculate=async()=>{if(!origin){setError('Set a starting point on the map first.');return}if(!destination){setError('Choose a VTA stop on the map first.');return}setCalculating(true);setError('');setResult(null);try{const response=await fetch(API+'/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin_latitude:origin[0],origin_longitude:origin[1],destination_stop_id:destination.stop_id,algorithm,profile})});const data=await response.json();if(!response.ok)throw new Error(detailOf(data));setResult(data);setStatus('Route calculated from the walking network')}catch(e){setError(messageOf(e));setStatus('Route could not be calculated')}finally{setCalculating(false)}}
  const locate=()=>{setError('');if(!navigator.geolocation){setError('Location is not available in this browser.');return}navigator.geolocation.getCurrentPosition(position=>{const next:[number,number]=[position.coords.latitude,position.coords.longitude];if(coverage){const R=6371000,lat0=coverage.center.latitude*Math.PI/180,lat1=next[0]*Math.PI/180,dlat=lat1-lat0,dlon=(next[1]-coverage.center.longitude)*Math.PI/180;const a=Math.sin(dlat/2)**2+Math.cos(lat0)*Math.cos(lat1)*Math.sin(dlon/2)**2;if(2*R*Math.asin(Math.sqrt(a))>coverage.radius_m){setError('Your current location is outside the supported area around Diridon Station.');return}}setOrigin(next);setResult(null);setStatus('Starting point set from your location')},e=>setError(e.code===1?'Location permission was denied.':e.code===2?'Your location is unavailable.':'Location request timed out.'),{enableHighAccuracy:true,timeout:12000,maximumAge:0})}
  const selectOnMap=()=>{setSelecting(true);setStatus('Click inside the map coverage to set your starting point')}
  const onMapOrigin=(point:[number,number])=>{setOrigin(point);setResult(null);setSelecting(false);setError('');setStatus('Starting point set')}
  const onSelectStop=(stop:Stop)=>{setDestination(stop);setResult(null);setError('');setStatus('Destination: '+stop.stop_name)}
  const routeFeature=useMemo(()=>result?({type:'Feature' as const,properties:{},geometry:result.geometry}):null,[result])
  return <main className="app-shell min-h-screen">
    <aside className="panel">
      <header className="brand"><div className="brand-mark" aria-hidden="true"><span/><span/><span/></div><div><div className="eyebrow">SAN JOSÉ · PHASE 1</div><h1>TransitGap</h1></div></header>
      <p className="intro">Find a walking route to transit. See what the map knows about stairs along the way.</p>
      <div className="coverage-line"><span className="live-dot"/><span>{loading?'Loading local datasets…':status}</span></div>
      {error&&<div className="notice error" role="alert">{error}{loading&&<span className="spinner"/>}</div>}
      <section className="controls" aria-label="Route controls">
        <div className="field-label">YOUR START</div>
        <div className="selection-row"><div className={'point-icon origin-icon '+(origin?'set':'')}>A</div><div className="selection-text">{origin?origin[0].toFixed(5)+', '+origin[1].toFixed(5):'Choose a point on the map'}</div></div>
        <div className="button-pair"><button className={'button '+(selecting?'button-active':'')} onClick={selectOnMap}>Set starting point</button><button className="button button-quiet" onClick={locate}>Use my location</button></div>
        <div className="field-label destination-label">YOUR DESTINATION</div>
        <div className="selection-row"><div className={'point-icon destination-icon '+(destination?'set':'')}>B</div><div className="selection-text">{destination?.stop_name||'Select a VTA stop on the map'}</div></div>
        <label className="field-label" htmlFor="algorithm">ROUTING ALGORITHM</label><select id="algorithm" value={algorithm} onChange={e=>setAlgorithm(e.target.value)}>{algorithms.map(x=><option value={x.value} key={x.value}>{x.label}</option>)}</select>
        <label className="field-label" htmlFor="profile">ROUTE PROFILE</label><select id="profile" value={profile} onChange={e=>setProfile(e.target.value)}>{profiles.map(x=><option value={x.value} key={x.value}>{x.label}</option>)}</select>
        <div className="button-pair actions"><button className="button button-primary" onClick={()=>void calculate()} disabled={calculating||loading}>{calculating?<><span className="spinner light"/> Calculating…</>:'Calculate route'}</button><button className="button button-quiet" onClick={clear}>Reset</button></div>
      </section>
      <section className="results" aria-live="polite"><div className="result-heading">ROUTE DETAILS</div>{result?<><div className="metrics"><div><strong>{(result.distance_m/1000).toFixed(2)}<small> km</small></strong><span>walking distance</span></div><div><strong>{Math.max(1,Math.round(result.duration_seconds/60))}<small> min</small></strong><span>at {result.walking_speed_mps_assumed.toFixed(1)} m/s assumed</span></div></div><div className="result-meta"><span>{algorithms.find(a=>a.value===result.algorithm)?.label}</span><span>{result.computation_time_ms.toFixed(1)} ms</span></div><div className="result-meta"><span>{result.graph_nodes_traversed} network nodes</span><span>{result.mapped_stair_segments} mapped stair segments</span></div><div className="notice warning">{result.accessibility_warning}</div></>:<p className="empty-result">Your route and network details will appear here.</p>}</section>
      <footer><span>OpenStreetMap · VTA GTFS</span><span>Map data may be incomplete</span></footer>
    </aside>
    <section className="map-shell" aria-label="Map and transit stops"><MapView coverage={coverage} stops={stops} origin={origin} destination={destination} route={routeFeature} selecting={selecting} onOrigin={onMapOrigin} onStop={onSelectStop}/><div className="map-topline"><span className="map-label">DIRIDON STATION AREA</span><span className="map-status">{loading?'Preparing map data':stops.length+' VTA stops'}</span></div><div className="map-hint">{selecting?'Click the map to place your start':'Select a VTA stop · Set your start on the map'}</div>{loading&&<div className="map-loading"><span className="spinner"/>Loading transit data</div>}</section>
  </main>
}
