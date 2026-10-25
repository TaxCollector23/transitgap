export type Entrance = {
  entrance_id: string;
  name: string;
  latitude: number;
  longitude: number;
  wheelchair_boarding: number;
};
export type Stop = {
  stop_id: string;
  stop_name: string;
  latitude: number;
  longitude: number;
  agency?: string;
  agency_name?: string;
  source_stop_id?: string;
  wheelchair_boarding?: number;
  station_id?: string | null;
  station_name?: string | null;
  platform_name?: string | null;
  direction?: string | null;
  stop_description?: string | null;
  stop_code?: string | null;
  headsigns?: string[];
  station_url?: string | null;
  routes_served?: string[];
  entrances?: Entrance[];
  modes?: string[];
};
export type Maneuver = {
  instruction: string;
  distance_m: number;
  status: string;
  warnings: string[];
  notes?: string[];
  maneuver?: string;
  kind?: string;
  name?: string | null;
  documented_concerns?: string[];
  missing_information?: string[];
  crossings?: { total: number; unmarked: number; signals: number; marked: number; unrecorded: number };
  segment_range?: [number, number] | null;
  location?: [number, number];
};
export type AccessibilitySummary = {
  headline: string;
  lines: string[];
  documented_restrictions: Array<{ code: string; text: string; steps: number[]; locations: string[] }>;
  missing_information: Array<{ attribute: string; label: string; distance_m: number; share: number | null }>;
  crossings: { total: number; unmarked: number; unrecorded_type: number };
  unmapped_connectors: Array<{ segment: number; distance_m: number; position: "start" | "end" }>;
  interpretation: string;
};
export type AttributeObservation = {
  attribute: string;
  observations: number;
  distance_m: number;
};
export type RouteAccessibility = {
  source: string;
  mapped_stair_segments: number;
  known_mapped_barrier_count: number;
  surface_distance_known_m: number;
  surface_distance_missing_m: number;
  distance_denominator_m: number;
  crossing_observations: {
    known_kerb_information: number;
    unknown_kerb_information: number;
    denominator: number;
  };
  documented_attributes: AttributeObservation[];
  missing_attributes: AttributeObservation[];
  interpretation: string;
};
export type RouteResult = {
  geometry: GeoJSON.Geometry;
  segments?: Array<{
    geometry: GeoJSON.Geometry;
    status: string;
    reasons: string[];
    length_m: number;
    name?: string | null;
    kind?: string;
    source?: string;
    osm_id?: number | number[] | null;
  }>;
  data_confidence?: number | null;
  directions?: Maneuver[];
  accessibility_summary?: AccessibilitySummary;
  arrival?: { type: "entrance" | "stop"; name?: string; latitude?: number; longitude?: number; note?: string | null; wheelchair_boarding?: number };
  reviewed_report_effects?: Array<Record<string, unknown>>;
  same_mapped_route_as_standard?: boolean;
  distance_m: number;
  duration_seconds: number;
  walking_speed_mps_assumed: number;
  algorithm: string;
  algorithm_warning?: string | null;
  profile: string;
  profile_explanation?: string;
  selected_edges?: Array<{from:string;to:string;key:string|null;reference:string}>;
  optimization_objective?: string;
  optimization_cost_m?: number;
  uncertainty_cost_m?: number;
  computation_time_ms: number;
  graph_nodes_traversed: number;
  mapped_stair_segments: number;
  accessibility?: RouteAccessibility;
  accessibility_warning: string;
  destination: Stop;
  groundtruth_evidence?: {
    status: string;
    nearby_feature_count: number | null;
    features: Array<{
      source_feature_id: string;
      distance_to_route_m: number;
      ada_compliance_record: string | null;
      width_record: string | null;
      last_update: string | null;
      status: string;
      relationship: string;
    }>;
    message: string;
  };
};
export type Coverage = {
  center: { latitude: number; longitude: number };
  radius_m: number;
  description: string;
  region?: string;
  bounds?: { west: number; south: number; east: number; north: number };
  boundary?:
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "MultiPolygon"; coordinates: number[][][][] };
};
export type GapFeature = {
  id: string;
  latitude: number;
  longitude: number;
  classification: string;
  category: string;
  explanation: string;
  priority_score: number | null;
  affected_vta_stop_count: number;
  missing_information: string[];
  matched_distance_m: number | null;
  provenance: {
    municipal_source: { status: string } | null;
    osm_source: { status: string } | null;
    interpretation: string;
  };
  nearby_stops?: Array<{ stop_id: string; stop_name: string; distance_m: number }>;
};

export type AdvocacySummary =
  | { status: "loading" }
  | { status: "calculating" }
  | { status: "unavailable" }
  | {
      status: "ready";
      nearbyStops: number;
      totalStops: number;
      radiusM: number;
      topStops: Array<{ stop_id: string; name: string; recordCount: number }>;
    };

export type ReachabilityStop = {
  stop_id: string;
  stop_name: string;
  latitude: number;
  longitude: number;
  connector_distance_m: number | null;
  direction?: string | null;
  platform_name?: string | null;
  routes_served?: string[];
};

export type ReachabilityAnalysis = {
  status: "OK" | "INSUFFICIENT_DOCUMENTED_DATA" | "STOP_CONNECTION_UNKNOWN" | "NO_SAMPLED_ORIGINS";
  version: string;
  study_area: { name: string; radius_m: number; center: { latitude: number; longitude: number } };
  stop: ReachabilityStop & { wheelchair_boarding?: number };
  gtfs_source: { url: string; feed_info: Array<Record<string, string>> };
  osm_source: { url: string; source_name: string; cache_file_modified_at: string | null; manifest_generated_at: string | null; source_snapshot_date: string | null; observation_timestamp: string | null };
  profile: string;
  profile_assumptions: { speed_mps: number; time_budget_minutes: number; maximum_stop_connector_m: number };
  sampling: { method: string; origin_sample_count: number; not_population_estimate: boolean };
  documented: { reachable_sample_origins: number; reachable_graph_nodes: number; reachable_edge_count: number; geometry: GeoJSON.FeatureCollection };
  possible: { reachable_sample_origins: number; reachable_graph_nodes: number; reachable_edge_count: number; geometry: GeoJSON.FeatureCollection };
  unknown_gap: { sample_origin_count: number; edge_count: number; critical_unknown_edge_count: number; geometry: GeoJSON.FeatureCollection; examples: Array<{ osm_way_id: string; source_url: string; missing_critical_attributes: string[]; evidence_status: string }> };
  example_paths: Array<{ origin_node: string; time_seconds: number; geometry: GeoJSON.Geometry; source_refs: Array<{ osm_way_id: string; url: string }> }>;
  inspection_priorities: {
    metric: string; method: string; candidate_limit: number; candidate_count_on_sample_paths: number;
    evaluated_candidate_count: number; sample_pair_count: number; parallel_edge_policy: string;
    candidates: Array<{ candidate_id: string; source_url: string; score: number | null; sample_count: number; status: string; affected_pairs: Array<[string, string]>; missing_critical_attributes: string[]; assumptions: string }>;
  };
  warnings: string[];
  message?: string;
};
export type Observation = {
  id: string;
  latitude: number;
  longitude: number;
  category: string;
  description: string | null;
  created_at: string;
  updated_at?: string;
  evidence_status: string;
  review_status: string;
};
export type SourceStatus = {
  sources: Array<{
    id: string;
    name: string;
    status: string;
    feature_count: number;
    url?: string | null;
    coverage_radius_m?: number;
  }>;
};
