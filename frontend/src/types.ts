export type Stop = { stop_id:string; stop_name:string; latitude:number; longitude:number }
export type RouteResult = { geometry:GeoJSON.Geometry; distance_m:number; duration_seconds:number; walking_speed_mps_assumed:number; algorithm:string; profile:string; computation_time_ms:number; graph_nodes_traversed:number; mapped_stair_segments:number; accessibility_warning:string; destination:Stop }
export type Coverage = { center:{latitude:number;longitude:number}; radius_m:number; description:string }
