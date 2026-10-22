import type {
  Direction,
  EscapeResponse,
  EscapeRoute,
  LatLon,
  RouteSegment,
  SearchPreferences,
  TrafficConfidence,
  TrafficSource,
} from './types';
import { lineDistanceKm, resolveRouteConfidence } from './utils';

interface SegmentSpec {
  start: number;
  end: number;
  road_name: string;
  highway: string;
  surface: string;
  road_stress: number;
  imd: number | null;
  heavy_pct: number | null;
  traffic_source: TrafficSource;
  traffic_year: number | null;
  traffic_confidence: TrafficConfidence;
}

interface RouteSpec {
  id: string;
  label: string;
  direction: Direction;
  escape_name: string;
  quiet_score: number;
  points: Array<[number, number]>;
  segments: SegmentSpec[];
}

/**
 * Datos simulados inspirados en Santiago de Compostela.
 * Las coordenadas son desplazamientos respecto al centro y se mueven con el
 * origen elegido, de modo que la demo funciona en cualquier punto del mapa.
 */
const ROUTE_SPECS: RouteSpec[] = [
  {
    id: 'oeste-roxos',
    label: 'Oeste vía Roxos',
    direction: 'W',
    escape_name: 'Roxos',
    quiet_score: 84,
    points: [
      [0, 0],
      [-0.01, -0.001],
      [-0.022, -0.003],
      [-0.04, -0.004],
      [-0.058, -0.005],
    ],
    segments: [
      {
        start: 0,
        end: 1,
        road_name: 'Rúa de San Pedro',
        highway: 'residential',
        surface: 'asphalt',
        road_stress: 74,
        imd: 9200,
        heavy_pct: 5.1,
        traffic_source: 'xunta',
        traffic_year: 2025,
        traffic_confidence: 'high',
      },
      {
        start: 1,
        end: 3,
        road_name: 'AC-543',
        highway: 'secondary',
        surface: 'asphalt',
        road_stress: 48,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
      {
        start: 3,
        end: 4,
        road_name: 'Camiño de Roxos',
        highway: 'tertiary',
        surface: 'asphalt',
        road_stress: 18,
        imd: 650,
        heavy_pct: 1.2,
        traffic_source: 'xunta',
        traffic_year: 2025,
        traffic_confidence: 'high',
      },
    ],
  },
  {
    id: 'norte-sigueiro',
    label: 'Norte hacia Sigüeiro',
    direction: 'N',
    escape_name: 'Salida norte',
    quiet_score: 78,
    points: [
      [0, 0],
      [-0.002, 0.012],
      [-0.006, 0.028],
      [-0.01, 0.048],
    ],
    segments: [
      {
        start: 0,
        end: 1,
        road_name: 'Rúa da Pastoriza',
        highway: 'residential',
        surface: 'asphalt',
        road_stress: 66,
        imd: 7100,
        heavy_pct: 3.4,
        traffic_source: 'xunta',
        traffic_year: 2025,
        traffic_confidence: 'high',
      },
      {
        start: 1,
        end: 2,
        road_name: 'CP-0201',
        highway: 'tertiary',
        surface: 'asphalt',
        road_stress: 44,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
      {
        start: 2,
        end: 3,
        road_name: 'Camiño de Sigüeiro',
        highway: 'tertiary',
        surface: 'asphalt',
        road_stress: 22,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
    ],
  },
  {
    id: 'sur-milladoiro',
    label: 'Sur hacia O Milladoiro',
    direction: 'S',
    escape_name: 'O Milladoiro',
    quiet_score: 63,
    points: [
      [0, 0],
      [0.002, -0.01],
      [0.006, -0.026],
      [0.01, -0.042],
    ],
    segments: [
      {
        start: 0,
        end: 1,
        road_name: 'N-550',
        highway: 'trunk',
        surface: 'asphalt',
        road_stress: 88,
        imd: 23000,
        heavy_pct: 9.8,
        traffic_source: 'mitma',
        traffic_year: 2022,
        traffic_confidence: 'medium',
      },
      {
        start: 1,
        end: 2,
        road_name: 'Rúa do Agro',
        highway: 'secondary',
        surface: 'asphalt',
        road_stress: 52,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
      {
        start: 2,
        end: 3,
        road_name: 'Camiño de O Milladoiro',
        highway: 'tertiary',
        surface: 'asphalt',
        road_stress: 26,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
    ],
  },
  {
    id: 'sureste-cacheiras',
    label: 'Sureste hacia Cacheiras',
    direction: 'SE',
    escape_name: 'Cacheiras',
    quiet_score: 86,
    points: [
      [0, 0],
      [-0.006, -0.015],
      [-0.022, -0.04],
      [-0.045, -0.065],
    ],
    segments: [
      {
        start: 0,
        end: 1,
        road_name: 'Rúa de Cacheiras',
        highway: 'residential',
        surface: 'asphalt',
        road_stress: 58,
        imd: 4800,
        heavy_pct: 2.1,
        traffic_source: 'xunta',
        traffic_year: 2025,
        traffic_confidence: 'high',
      },
      {
        start: 1,
        end: 2,
        road_name: 'AC-841',
        highway: 'tertiary',
        surface: 'asphalt',
        road_stress: 35,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
      {
        start: 2,
        end: 3,
        road_name: 'Camiño de Cacheiras',
        highway: 'tertiary',
        surface: 'asphalt',
        road_stress: 15,
        imd: 320,
        heavy_pct: 0.8,
        traffic_source: 'xunta',
        traffic_year: 2025,
        traffic_confidence: 'high',
      },
    ],
  },
  {
    id: 'este-arins',
    label: 'Este hacia Aríns',
    direction: 'E',
    escape_name: 'Aríns',
    quiet_score: 76,
    points: [
      [0, 0],
      [0.01, -0.002],
      [0.026, -0.004],
      [0.046, -0.006],
    ],
    segments: [
      {
        start: 0,
        end: 1,
        road_name: 'Rúa de Aríns',
        highway: 'residential',
        surface: 'asphalt',
        road_stress: 70,
        imd: 6100,
        heavy_pct: 3.0,
        traffic_source: 'xunta',
        traffic_year: 2025,
        traffic_confidence: 'high',
      },
      {
        start: 1,
        end: 2,
        road_name: 'AC-260',
        highway: 'secondary',
        surface: 'asphalt',
        road_stress: 46,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
      {
        start: 2,
        end: 3,
        road_name: 'Camiño de Aríns',
        highway: 'tertiary',
        surface: 'asphalt',
        road_stress: 24,
        imd: null,
        heavy_pct: null,
        traffic_source: 'osm_estimate',
        traffic_year: null,
        traffic_confidence: 'low',
      },
    ],
  },
];

function buildRoute(
  spec: RouteSpec,
  origin: LatLon,
  prefs: SearchPreferences,
): EscapeRoute {
  // Los puntos de las plantillas son desplazamientos respecto al origen:
  // se suman a la posición elegida, no al centro de Santiago.
  const shift = ([lon, lat]: [number, number]): [number, number] => [
    lon + origin.lon,
    lat + origin.lat,
  ];

  const points = spec.points.map(shift);
  const totalKm = lineDistanceKm(points);

  const segments: RouteSegment[] = spec.segments.map((segment) => ({
    geometry: {
      type: 'LineString',
      coordinates: points.slice(segment.start, segment.end + 1),
    },
    road_name: segment.road_name,
    highway: segment.highway,
    surface: segment.surface,
    road_stress: segment.road_stress,
    imd: segment.imd,
    heavy_pct: segment.heavy_pct,
    traffic_source: segment.traffic_source,
    traffic_year: segment.traffic_year,
    traffic_confidence: segment.traffic_confidence,
  }));

  const measuredKm = segments
    .filter((segment) => segment.traffic_source !== 'osm_estimate')
    .reduce((total, segment) => total + lineDistanceKm(segment.geometry.coordinates), 0);
  const measuredShare = totalKm > 0 ? measuredKm / totalKm : 0;
  const years = Array.from(
    new Set(
      segments
        .map((segment) => segment.traffic_year)
        .filter((year): year is number => year !== null),
    ),
  );
  const sources = Array.from(new Set(segments.map((segment) => segment.traffic_source)));

  const confidence = resolveRouteConfidence(measuredShare, years, segments, 'low');

  const avgStress =
    totalKm > 0
      ? segments.reduce(
          (total, segment) =>
            total +
            segment.road_stress * lineDistanceKm(segment.geometry.coordinates),
          0,
        ) / totalKm
      : 0;

  const escape = points[points.length - 1];

  return {
    id: spec.id,
    label: spec.label,
    direction: spec.direction,
    is_recommended: false,
    escape_time_min: Math.max(
      3,
      Math.round((totalKm / prefs.avgSpeedKmh) * 60),
    ),
    distance_to_escape_km: Math.round(totalKm * 10) / 10,
    quiet_score: spec.quiet_score,
    avg_road_stress: Math.round(avgStress),
    escape_point: { lat: escape[1], lon: escape[0], name: spec.escape_name },
    geometry: { type: 'LineString', coordinates: points },
    segments,
    traffic_summary: {
      sources,
      years,
      measured_share: Math.round(measuredShare * 100) / 100,
      confidence,
    },
    warnings: segments.some((segment) => segment.traffic_source === 'osm_estimate')
      ? ['Incluye tramos sin aforo estimados con OSM']
      : [],
  };
}

function scoreRoute(route: EscapeRoute, prefs: SearchPreferences): number {
  // λ = 0 prioriza rapidez; λ = 1 prioriza tranquilidad.
  const lambda = Math.min(1, Math.max(0, prefs.trafficLambda));
  const quietWeight = (0.15 + lambda * 2.1) * (1 + prefs.trafficAversion * 0.6);
  const timeWeight = 2.6 - lambda * 2.45;
  return route.quiet_score * quietWeight - route.escape_time_min * timeWeight;
}

export async function buildMockResponse(
  origin: LatLon,
  prefs: SearchPreferences,
): Promise<EscapeResponse> {
  await new Promise((resolve) => window.setTimeout(resolve, 420));

  const routes = ROUTE_SPECS.map((spec) => buildRoute(spec, origin, prefs)).sort(
    (a, b) => scoreRoute(b, prefs) - scoreRoute(a, prefs),
  );

  if (routes.length > 0) {
    routes[0] = { ...routes[0], is_recommended: true };
  }

  return {
    schema_version: '0.1',
    request_id: `mock_${Date.now()}`,
    generated_at: new Date().toISOString(),
    origin,
    recommended_route_id: routes[0]?.id ?? '',
    routes,
    warnings: [
      'Datos de ejemplo: geometrías y aforos simulados para la demo.',
    ],
  };
}
