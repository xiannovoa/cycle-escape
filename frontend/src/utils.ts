import type {
  LineStringGeometry,
  TrafficConfidence,
  TrafficSource,
} from './types';

export const STRESS_BANDS = [
  { max: 25, color: '#1f9d55', label: 'Tranquilo' },
  { max: 50, color: '#e0b416', label: 'Transición' },
  { max: 75, color: '#ee7d1f', label: 'Estrés medio-alto' },
  { max: 100, color: '#d93636', label: 'Estrés alto' },
];

export function stressColor(stress: number): string {
  const band = STRESS_BANDS.find((item) => stress <= item.max);
  return band?.color ?? STRESS_BANDS[STRESS_BANDS.length - 1].color;
}

export function stressLabel(stress: number): string {
  return STRESS_BANDS.find((item) => stress <= item.max)?.label ?? 'Estrés alto';
}

export function quietScoreColor(score: number): string {
  if (score >= 75) return '#1f9d55';
  if (score >= 55) return '#c98a0b';
  return '#d93636';
}

export function geojsonToLatLngs(geometry: LineStringGeometry): Array<[number, number]> {
  return geometry.coordinates.map(([lon, lat]) => [lat, lon]);
}

export function formatKm(value: number): string {
  return value.toFixed(1);
}

export function formatMinutes(value: number): string {
  return String(Math.round(value));
}

export function sourceLabel(source: TrafficSource): string {
  switch (source) {
    case 'xunta':
      return 'Xunta';
    case 'mitma':
      return 'MITMA';
    case 'osm_estimate':
      return 'OSM estimado';
  }
}

export function confidenceLabel(confidence: TrafficConfidence): string {
  switch (confidence) {
    case 'high':
      return 'alta';
    case 'medium':
      return 'media';
    case 'low':
      return 'baja';
  }
}

/** Cobertura medida máxima para confianza media (1–2%). */
export const CONFIDENCE_MEDIUM_MAX_MEASURED_SHARE = 0.02;

/**
 * Confianza de ruta según la cobertura medida:
 * 0% → baja, 1–2% → media, más de 2% → alta.
 */
export function resolveRouteConfidence(measuredShare: number): TrafficConfidence {
  if (measuredShare === 0) return 'low';
  if (measuredShare <= CONFIDENCE_MEDIUM_MAX_MEASURED_SHARE) return 'medium';
  return 'high';
}

export function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[character] ?? character,
  );
}

export function haversineKm(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number },
): number {
  const radius = 6371;
  const toRad = (degrees: number) => (degrees * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(h));
}

export function lineDistanceKm(coordinates: Array<[number, number]>): number {
  let total = 0;
  for (let index = 1; index < coordinates.length; index += 1) {
    const [lonA, latA] = coordinates[index - 1];
    const [lonB, latB] = coordinates[index];
    total += haversineKm({ lat: latA, lon: lonA }, { lat: latB, lon: lonB });
  }
  return total;
}

export function directionArrow(direction: string): string {
  const arrows: Record<string, string> = {
    N: '↑',
    NE: '↗',
    E: '→',
    SE: '↘',
    S: '↓',
    SW: '↙',
    W: '←',
    NW: '↖',
  };
  return arrows[direction] ?? '•';
}
