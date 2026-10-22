import type { LatLon } from './types';

export interface ReverseGeocodeResult {
  name: string;
  locality: string;
}

interface NominatimAddress {
  road?: string;
  pedestrian?: string;
  footway?: string;
  cycleway?: string;
  path?: string;
  square?: string;
  neighbourhood?: string;
  suburb?: string;
  city?: string;
  town?: string;
  village?: string;
  municipality?: string;
  county?: string;
}

interface NominatimResponse {
  name?: string;
  display_name?: string;
  address?: NominatimAddress;
}

interface NominatimPlace extends NominatimResponse {
  lat?: string;
  lon?: string;
}

export interface StreetSearchResult extends ReverseGeocodeResult {
  origin: LatLon;
}

function firstNonEmpty(...values: Array<string | undefined>): string {
  return values.find((value) => Boolean(value && value.trim()))?.trim() ?? '';
}

function parsePlace(data: NominatimPlace): ReverseGeocodeResult | null {
  const address = data.address ?? {};
  const name = firstNonEmpty(
    address.road,
    address.pedestrian,
    address.footway,
    address.cycleway,
    address.path,
    address.square,
    address.neighbourhood,
    address.suburb,
    data.name,
    data.display_name?.split(',')[0],
  );
  const locality = firstNonEmpty(
    address.city,
    address.town,
    address.village,
    address.municipality,
    address.county,
  );

  return name ? { name, locality } : null;
}

/**
 * Geocodificación inversa con Nominatim (OpenStreetMap).
 * No requiere clave. Si falla, el llamador decide el texto de respaldo.
 */
export async function reverseGeocode(
  origin: LatLon,
  signal?: AbortSignal,
): Promise<ReverseGeocodeResult | null> {
  if (signal?.aborted) return null;

  const params = new URLSearchParams({
    format: 'jsonv2',
    lat: String(origin.lat),
    lon: String(origin.lon),
    zoom: '18',
    addressdetails: '1',
    'accept-language': 'es',
  });

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4000);
  const abortFromCaller = () => controller.abort();
  signal?.addEventListener('abort', abortFromCaller);

  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/reverse?${params.toString()}`,
      {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      },
    );

    if (!response.ok) return null;

    const data = (await response.json()) as NominatimResponse;
    return parsePlace(data);
  } catch {
    return null;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}

/**
 * Búsqueda de una calle o lugar para usarlo como origen.
 * Se sesga la búsqueda al entorno de Santiago sin bloquear resultados cercanos.
 */
export async function searchStreet(
  query: string,
  signal?: AbortSignal,
): Promise<StreetSearchResult | null> {
  const trimmed = query.trim();
  if (!trimmed || signal?.aborted) return null;

  const params = new URLSearchParams({
    format: 'jsonv2',
    q: trimmed,
    addressdetails: '1',
    limit: '5',
    countrycodes: 'es',
    viewbox: '-8.75,43.00,-8.35,42.80',
    bounded: '0',
    'accept-language': 'es',
  });

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5000);
  const abortFromCaller = () => controller.abort();
  signal?.addEventListener('abort', abortFromCaller);

  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?${params.toString()}`,
      {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      },
    );

    if (!response.ok) return null;

    const data = (await response.json()) as NominatimPlace[];
    if (!Array.isArray(data)) return null;

    for (const place of data) {
      const lat = Number(place.lat);
      const lon = Number(place.lon);
      const parsed = parsePlace(place);
      if (parsed && Number.isFinite(lat) && Number.isFinite(lon)) {
        return { ...parsed, origin: { lat, lon } };
      }
    }

    return null;
  } catch {
    return null;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}
