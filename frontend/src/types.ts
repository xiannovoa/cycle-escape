export interface LatLon {
  lat: number;
  lon: number;
}

export type TrafficSource = 'xunta' | 'mitma' | 'osm_estimate';
export type TrafficConfidence = 'high' | 'medium' | 'low';
export type SurfacePreference = 'asphalt' | 'mixed' | 'any';
export type RoutePreference = 'direct' | 'balanced' | 'quiet';
export type Direction = 'N' | 'NE' | 'E' | 'SE' | 'S' | 'SW' | 'W' | 'NW';

export interface LineStringGeometry {
  type: 'LineString';
  coordinates: Array<[number, number]>;
}

export interface RouteSegment {
  geometry: LineStringGeometry;
  road_name: string | null;
  highway: string | null;
  surface: string | null;
  road_stress: number;
  imd: number | null;
  heavy_pct: number | null;
  traffic_source: TrafficSource;
  traffic_year: number | null;
  traffic_confidence: TrafficConfidence;
}

export interface TrafficSummary {
  sources: TrafficSource[];
  years: number[];
  measured_share: number;
  confidence: TrafficConfidence;
}

export interface EscapePoint {
  lat: number;
  lon: number;
  name: string;
}

export interface EscapeRoute {
  id: string;
  label: string;
  direction: Direction;
  is_recommended: boolean;
  escape_time_min: number;
  distance_to_escape_km: number;
  quiet_score: number;
  avg_road_stress: number;
  escape_point: EscapePoint;
  geometry: LineStringGeometry;
  segments: RouteSegment[];
  traffic_summary: TrafficSummary;
  warnings: string[];
}

export interface EscapeResponse {
  schema_version: string;
  request_id: string;
  generated_at: string;
  origin: LatLon;
  recommended_route_id: string;
  routes: EscapeRoute[];
  warnings: string[];
}

export interface SearchPreferences {
  avgSpeedKmh: number;
  trafficAversion: number;
  trafficLambda: number;
  surfacePreference: SurfacePreference;
}

export interface EscapeRequest {
  origin: LatLon;
  avg_speed_kmh: number;
  traffic_aversion: number;
  traffic_lambda: number;
  surface_preference: SurfacePreference;
  route_preference: RoutePreference;
  max_candidates: number;
}

export interface SearchResult {
  response: EscapeResponse;
  source: 'live';
}
