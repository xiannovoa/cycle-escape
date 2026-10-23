import { resolveRouteConfidence } from './utils';
import type {
  EscapeResponse,
  EscapeRoute,
  LatLon,
  RouteSegment,
  RoutePreference,
  SearchPreferences,
  SearchResult,
  TrafficConfidence,
  TrafficSource,
} from './types';

const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(
  /\/+$/,
  '',
);

export class EscapeApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status = 0) {
    super(message);
    this.name = 'EscapeApiError';
    this.code = code;
    this.status = status;
  }
}

function clampStress(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)));
}

function normalizeSegment(
  segment: RouteSegment,
  fallbackSource: TrafficSource,
  fallbackConfidence: TrafficConfidence,
): RouteSegment {
  return {
    geometry: segment.geometry,
    road_name: segment.road_name ?? null,
    highway: segment.highway ?? null,
    surface: segment.surface ?? null,
    road_stress: clampStress(Number(segment.road_stress) || 0),
    imd: typeof segment.imd === 'number' ? segment.imd : null,
    heavy_pct: typeof segment.heavy_pct === 'number' ? segment.heavy_pct : null,
    traffic_source: segment.traffic_source ?? fallbackSource,
    traffic_year: typeof segment.traffic_year === 'number' ? segment.traffic_year : null,
    traffic_confidence: segment.traffic_confidence ?? fallbackConfidence,
  };
}

function normalizeRoute(route: EscapeRoute, index: number): EscapeRoute {
  const geometry = route.geometry;
  if (
    !geometry ||
    geometry.type !== 'LineString' ||
    !Array.isArray(geometry.coordinates) ||
    geometry.coordinates.length < 2
  ) {
    throw new Error('Una ruta no incluye una geometría LineString válida');
  }

  const summary = route.traffic_summary;
  const fallbackSource: TrafficSource = summary?.sources?.[0] ?? 'osm_estimate';
  const fallbackConfidence: TrafficConfidence = summary?.confidence ?? 'low';
  const last = geometry.coordinates[geometry.coordinates.length - 1];

  const segments =
    Array.isArray(route.segments) && route.segments.length > 0
      ? route.segments.map((segment) =>
          normalizeSegment(segment, fallbackSource, fallbackConfidence),
        )
      : [
          {
            geometry,
            road_name: null,
            highway: null,
            surface: null,
            road_stress: clampStress(Number(route.avg_road_stress) || 0),
            imd: null,
            heavy_pct: null,
            traffic_source: fallbackSource,
            traffic_year: null,
            traffic_confidence: fallbackConfidence,
          },
        ];

  const years =
    summary?.years ??
    segments
      .map((segment) => segment.traffic_year)
      .filter((year): year is number => year !== null);
  const measuredShare = summary?.measured_share ?? 0;
  const confidence = resolveRouteConfidence(measuredShare);

  return {
    ...route,
    id: route.id || `route-${index}`,
    label: route.label || `Corredor ${index + 1}`,
    direction: route.direction ?? 'N',
    is_recommended: Boolean(route.is_recommended),
    escape_time_min: Number(route.escape_time_min) || 0,
    distance_to_escape_km: Number(route.distance_to_escape_km) || 0,
    quiet_score: clampStress(Number(route.quiet_score) || 0),
    avg_road_stress: clampStress(Number(route.avg_road_stress) || 0),
    escape_point: {
      lat: route.escape_point?.lat ?? last[1],
      lon: route.escape_point?.lon ?? last[0],
      name: route.escape_point?.name?.trim() || 'Escape Point',
    },
    geometry,
    segments,
    traffic_summary: {
      sources: summary?.sources ?? [fallbackSource],
      years,
      measured_share: measuredShare,
      confidence,
    },
    warnings: Array.isArray(route.warnings) ? route.warnings : [],
  };
}

function normalizeResponse(raw: EscapeResponse, fallbackOrigin: LatLon): EscapeResponse {
  if (!raw || !Array.isArray(raw.routes) || raw.routes.length === 0) {
    throw new EscapeApiError(
      'NO_ROUTES_FOUND',
      'No hay rutas disponibles para este origen.',
      404,
    );
  }

  const routes = raw.routes.map(normalizeRoute);

  const recommended =
    raw.recommended_route_id && routes.some((route) => route.id === raw.recommended_route_id)
      ? raw.recommended_route_id
      : routes[0].id;

  routes.forEach((route) => {
    route.is_recommended = route.id === recommended;
  });

  return {
    schema_version: raw.schema_version ?? '0.1',
    request_id: raw.request_id ?? `live_${Date.now()}`,
    generated_at: raw.generated_at ?? new Date().toISOString(),
    origin: raw.origin ?? fallbackOrigin,
    recommended_route_id: recommended,
    routes,
    warnings: Array.isArray(raw.warnings) ? raw.warnings : [],
  };
}

export async function searchEscapeRoutes(
  origin: LatLon,
  prefs: SearchPreferences,
): Promise<SearchResult> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 6500);

  // Se mantiene route_preference por compatibilidad con el contrato;
  // traffic_lambda añade el peso continuo del componente de tráfico.
  const routePreference: RoutePreference =
    prefs.trafficLambda < 0.34
      ? 'direct'
      : prefs.trafficLambda > 0.66
        ? 'quiet'
        : 'balanced';

  try {
    const response = await fetch(`${API_BASE}/api/escape-routes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        origin,
        avg_speed_kmh: prefs.avgSpeedKmh,
        traffic_aversion: prefs.trafficAversion,
        traffic_lambda: prefs.trafficLambda,
        surface_preference: prefs.surfacePreference,
        route_preference: routePreference,
        max_candidates: 5,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      interface ApiErrorBody {
        error?: { code?: string; message?: string };
      }
      let detail: ApiErrorBody | null = null;
      try {
        detail = (await response.json()) as ApiErrorBody;
      } catch {
        detail = null;
      }
      throw new EscapeApiError(
        detail?.error?.code ?? 'API_ERROR',
        detail?.error?.message ?? `La API respondió con HTTP ${response.status}.`,
        response.status,
      );
    }

    const raw = (await response.json()) as EscapeResponse;
    return { response: normalizeResponse(raw, origin), source: 'live' };
  } catch (error) {
    if (error instanceof EscapeApiError) throw error;
    if (error instanceof Error && error.name === 'AbortError') {
      throw new EscapeApiError(
        'TIMEOUT',
        'La API tardó demasiado en responder. Inténtalo de nuevo.',
      );
    }
    throw new EscapeApiError(
      'NETWORK_ERROR',
      'No se pudo conectar con la API. Comprueba que el backend esté levantado.',
    );
  } finally {
    window.clearTimeout(timeout);
  }
}
