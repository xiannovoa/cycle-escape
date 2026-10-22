import type { SearchPreferences, SurfacePreference } from './types';

export interface RiderProfile {
  name: string;
  avgSpeedKmh: number;
  trafficAversion: number;
  trafficLambda: number;
  surfacePreference: SurfacePreference;
}

const STORAGE_KEY = 'cycle-escape.profile.v1';

export const DEFAULT_PROFILE: RiderProfile = {
  name: 'Ciclista',
  avgSpeedKmh: 22,
  trafficAversion: 0.5,
  trafficLambda: 0.5,
  surfacePreference: 'asphalt',
};

function clamp(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

/**
 * Un único slider 0–1 controla prioridad y aversión:
 * 0 = salida rápida y tolera tráfico; 1 = salida lenta y evita tráfico.
 */
export function trafficAversionForPreference(value: number): number {
  const preference = Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0.5));
  return 0.2 + preference * 0.65;
}

export function normalizeProfile(input: Partial<RiderProfile>): RiderProfile {
  const surface =
    input.surfacePreference === 'mixed' || input.surfacePreference === 'any'
      ? input.surfacePreference
      : 'asphalt';

  const trafficLambda = clamp(
    input.trafficLambda ?? DEFAULT_PROFILE.trafficLambda,
    0,
    1,
    0.5,
  );

  return {
    name: (input.name ?? DEFAULT_PROFILE.name).trim().slice(0, 40) || DEFAULT_PROFILE.name,
    avgSpeedKmh: clamp(input.avgSpeedKmh ?? DEFAULT_PROFILE.avgSpeedKmh, 10, 40, 22),
    trafficAversion: trafficAversionForPreference(trafficLambda),
    trafficLambda,
    surfacePreference: surface,
  };
}

export function profileToPrefs(profile: RiderProfile): SearchPreferences {
  return {
    avgSpeedKmh: profile.avgSpeedKmh,
    trafficAversion: trafficAversionForPreference(profile.trafficLambda),
    trafficLambda: profile.trafficLambda,
    surfacePreference: profile.surfacePreference,
  };
}

export function loadProfile(): RiderProfile | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<RiderProfile>;
    return normalizeProfile(parsed);
  } catch {
    return null;
  }
}

export function saveProfile(profile: RiderProfile): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeProfile(profile)));
  } catch {
    // Si el navegador bloquea localStorage, el perfil sigue en memoria.
  }
}
