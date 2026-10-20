export type Stop = {
  stop_id: string;
  stop_name: string;
  latitude: number;
  longitude: number;
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
  }>;
  data_confidence?: number | null;
  directions?: Array<{
    instruction: string;
    distance_m: number;
    status: string;
    warnings: string[];
  }>;
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
