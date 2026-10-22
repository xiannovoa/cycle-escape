import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { EscapeApiError, searchEscapeRoutes } from './api';
import { InfoModal } from './components/InfoModal';
import { Legend } from './components/Legend';
import { MapView } from './components/MapView';
import { Onboarding } from './components/Onboarding';
import { ResultsPanel } from './components/ResultsPanel';
import { SettingsModal } from './components/SettingsModal';
import { reverseGeocode, searchStreet } from './geocode';
import {
  DEFAULT_PROFILE,
  loadProfile,
  normalizeProfile,
  profileToPrefs,
  saveProfile,
  type RiderProfile,
} from './profile';
import type { EscapeResponse, LatLon, SearchPreferences } from './types';

const DEFAULT_ORIGIN: LatLon = { lat: 42.8782, lon: -8.5448 };

type ViewMode = 'desktop' | 'mobile';

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>(() =>
    window.matchMedia('(max-width: 700px)').matches ? 'mobile' : 'desktop',
  );
  const [profile, setProfile] = useState<RiderProfile | null>(() => loadProfile());
  const [prefs, setPrefs] = useState<SearchPreferences>(() =>
    profileToPrefs(loadProfile() ?? DEFAULT_PROFILE),
  );
  const [origin, setOrigin] = useState<LatLon>(DEFAULT_ORIGIN);
  const [hasOrigin, setHasOrigin] = useState(false);
  const [data, setData] = useState<EscapeResponse | null>(null);
  const [source, setSource] = useState<'live' | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [originName, setOriginName] = useState('Santiago de Compostela');
  const [originLocality, setOriginLocality] = useState('Santiago de Compostela');
  const [geocoding, setGeocoding] = useState(false);
  const [streetQuery, setStreetQuery] = useState('');
  const [streetSearching, setStreetSearching] = useState(false);
  const [streetError, setStreetError] = useState<string | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const requestId = useRef(0);
  const geocodeRequestId = useRef(0);
  const skipNextGeocode = useRef(false);
  const toastTimer = useRef<number | null>(null);

  function showToast(message: string) {
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    setToast(message);
    toastTimer.current = window.setTimeout(() => {
      setToast(null);
      toastTimer.current = null;
    }, 6000);
  }

  useEffect(
    () => () => {
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    },
    [],
  );

  async function runSearch(nextOrigin: LatLon, nextPrefs: SearchPreferences) {
    const currentRequest = requestId.current + 1;
    requestId.current = currentRequest;
    setLoading(true);
    setError(null);
    setToast(null);

    try {
      const result = await searchEscapeRoutes(nextOrigin, nextPrefs);
      if (currentRequest !== requestId.current) return;

      setData(result.response);
      setSource(result.source);
      setSelectedId(null);
    } catch (searchError) {
      if (currentRequest !== requestId.current) return;

      if (searchError instanceof EscapeApiError) {
        if (
          searchError.code === 'OUTSIDE_COVERAGE' ||
          searchError.code === 'NO_ROUTES_FOUND'
        ) {
          setData(null);
          setSource(null);
          setSelectedId(null);
          showToast('No hay datos de carreteras para esta zona. Prueba con otro origen.');
          return;
        }
        if (searchError.code === 'DATA_NOT_READY') {
          setData(null);
          setSource(null);
          setSelectedId(null);
          showToast('El backend todavía no tiene datos cargados.');
          return;
        }
        setError(searchError.message);
        return;
      }

      console.error(searchError);
      setError('No se pudieron calcular los corredores. Inténtalo de nuevo.');
    } finally {
      if (currentRequest === requestId.current) {
        setLoading(false);
      }
    }
  }

  function clearResults() {
    requestId.current += 1;
    setLoading(false);
    setData(null);
    setSource(null);
    setSelectedId(null);
    setError(null);
    setToast(null);
  }

  useEffect(() => {
    if (skipNextGeocode.current) {
      skipNextGeocode.current = false;
      setGeocoding(false);
      return;
    }

    const currentRequest = geocodeRequestId.current + 1;
    geocodeRequestId.current = currentRequest;
    const controller = new AbortController();

    const timer = window.setTimeout(async () => {
      setGeocoding(true);
      const result = await reverseGeocode(origin, controller.signal);
      if (controller.signal.aborted || currentRequest !== geocodeRequestId.current) return;

      if (result) {
        setOriginName(result.name);
        setOriginLocality(result.locality);
      } else {
        const isDefault =
          Math.abs(origin.lat - DEFAULT_ORIGIN.lat) < 0.0005 &&
          Math.abs(origin.lon - DEFAULT_ORIGIN.lon) < 0.0005;
        setOriginName(isDefault ? 'Santiago de Compostela' : 'Punto seleccionado');
        setOriginLocality(isDefault ? 'Santiago de Compostela' : '');
      }

      setGeocoding(false);
    }, 900);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [origin]);

  function handleOriginChange(nextOrigin: LatLon) {
    setOrigin(nextOrigin);
    setHasOrigin(true);
    setGeocoding(true);
    setStreetError(null);
    clearResults();
    void runSearch(nextOrigin, prefs);
  }

  async function handleStreetSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = streetQuery.trim();
    if (!query || streetSearching) return;

    setStreetSearching(true);
    setStreetError(null);

    const result = await searchStreet(query);
    setStreetSearching(false);

    if (!result) {
      setStreetError('No encontramos esa calle. Prueba con más detalle.');
      return;
    }

    skipNextGeocode.current = true;
    setOrigin(result.origin);
    setHasOrigin(true);
    setOriginName(result.name);
    setOriginLocality(result.locality);
    setGeocoding(false);
    setStreetQuery('');
    clearResults();
    void runSearch(result.origin, prefs);
  }

  function handleProfileComplete(nextProfile: RiderProfile) {
    const normalized = normalizeProfile(nextProfile);
    saveProfile(normalized);
    setProfile(normalized);
    setPrefs(profileToPrefs(normalized));
  }

  function handleSettingsSave(nextProfile: RiderProfile) {
    const normalized = normalizeProfile(nextProfile);
    const nextPrefs = profileToPrefs(normalized);
    saveProfile(normalized);
    setProfile(normalized);
    setPrefs(nextPrefs);
    setSettingsOpen(false);
    clearResults();
    if (hasOrigin) {
      void runSearch(origin, nextPrefs);
    }
  }

  const selectedRoute = data?.routes.find((route) => route.id === selectedId) ?? null;
  const originHint = geocoding
    ? 'OpenStreetMap'
    : `${originLocality && originLocality !== originName ? `${originLocality} · ` : ''}Toca el mapa para cambiar el origen`;
  const sourceLabelText = source === 'live' ? 'Datos en vivo' : 'Sin buscar';

  if (!profile) {
    return <Onboarding onComplete={handleProfileComplete} />;
  }

  return (
    <div className={`app app--${viewMode}`}>
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M4.5 18.5c0-4.2 4.4-4.2 4.4-8.2 0-3.6 4.1-3.6 4.1-6.8"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              />
              <circle cx="4.5" cy="18.5" r="2.2" fill="currentColor" />
              <circle cx="13" cy="3.5" r="2.2" fill="currentColor" />
            </svg>
          </span>
          <div className="brand__text">
            <h1>Cyclout</h1>
            <p>Sal de la ciudad. Encuentra carreteras tranquilas.</p>
          </div>
        </div>

        <div className="topbar__meta">
          <span className={`source-badge source-badge--${source ?? 'loading'}`}>
            <i />
            {sourceLabelText}
          </span>
          <span className="city-badge">Santiago de Compostela</span>

          <div className="view-switch" role="group" aria-label="Vista de la aplicación">
            <button
              type="button"
              className={viewMode === 'desktop' ? 'is-active' : ''}
              onClick={() => setViewMode('desktop')}
              aria-pressed={viewMode === 'desktop'}
              title="Vista PC"
            >
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect
                  x="3"
                  y="4"
                  width="18"
                  height="12"
                  rx="1.5"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path d="M12 16v4M8 20h8" stroke="currentColor" strokeWidth="2" />
              </svg>
            </button>
            <button
              type="button"
              className={viewMode === 'mobile' ? 'is-active' : ''}
              onClick={() => setViewMode('mobile')}
              aria-pressed={viewMode === 'mobile'}
              title="Vista móvil"
            >
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect
                  x="7"
                  y="2.5"
                  width="10"
                  height="19"
                  rx="2"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path d="M11 18.5h2" stroke="currentColor" strokeWidth="2" />
              </svg>
            </button>
          </div>

          <button
            type="button"
            className="info-button"
            onClick={() => setInfoOpen(true)}
            aria-haspopup="dialog"
          >
            <span className="info-button__icon" aria-hidden="true">
              i
            </span>
            <span className="button-label">Información</span>
          </button>
          <button
            type="button"
            className="settings-button"
            onClick={() => setSettingsOpen(true)}
            aria-haspopup="dialog"
          >
            <span className="settings-button__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M4 7h16M4 17h16" stroke="currentColor" strokeWidth="2" />
                <circle cx="9" cy="7" r="2.2" fill="currentColor" />
                <circle cx="15" cy="17" r="2.2" fill="currentColor" />
              </svg>
            </span>
            <span className="button-label">Ajustes</span>
          </button>
        </div>
      </header>

      <main className="app__main">
        <aside className="sidebar">
          <section className="origin-card" aria-label="Origen de la ruta">
            <div className="origin-card__top">
              <span className="eyebrow">Origen</span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => handleOriginChange(DEFAULT_ORIGIN)}
              >
                Volver a Santiago
              </button>
            </div>
            <strong
              className="origin-card__name"
              title={
                hasOrigin
                  ? `${origin.lat.toFixed(4)}, ${origin.lon.toFixed(4)}`
                  : undefined
              }
            >
              {!hasOrigin
                ? 'Marca tu posición'
                : geocoding
                  ? 'Buscando calle…'
                  : originName}
            </strong>
            <form className="origin-search" onSubmit={(event) => void handleStreetSubmit(event)}>
              <input
                type="text"
                value={streetQuery}
                placeholder="Escribe una calle o lugar…"
                aria-label="Buscar calle de origen"
                disabled={streetSearching}
                onChange={(event) => {
                  setStreetQuery(event.target.value);
                  setStreetError(null);
                }}
              />
              <button
                type="submit"
                disabled={streetSearching || streetQuery.trim().length === 0}
              >
                {streetSearching ? '…' : 'Ir'}
              </button>
            </form>
            <small>
              {hasOrigin
                ? originHint
                : 'Toca el mapa o busca una calle para empezar'}
            </small>
            {streetError && <small className="origin-error">{streetError}</small>}
          </section>

          {error && (
            <div className="notice notice--error">
              <span>{error}</span>
              <button
                type="button"
                className="notice__retry"
                onClick={() => void runSearch(origin, prefs)}
              >
                Reintentar
              </button>
            </div>
          )}

          {loading && !data && (
            <div className="skeleton-list" aria-hidden="true">
              <div className="skeleton-card" />
              <div className="skeleton-card" />
              <div className="skeleton-card" />
            </div>
          )}

          {!loading && !data && !error && (
            <div className="empty-state">
              <strong>Marca tu posición</strong>
              <p>
                Toca el mapa o busca una calle. Las salidas aparecerán automáticamente.
              </p>
            </div>
          )}

          {data && (
            <ResultsPanel
              routes={data.routes}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}

          <footer className="sidebar__foot">
            <p>
              El Road Stress es una estimación de estrés viario y exposición al tráfico.
              No es un <em>safety score</em>.
            </p>
            <p className="sidebar__attribution">
              © OpenStreetMap contributors · Aforos: Xunta de Galicia / MITMA
            </p>
          </footer>
        </aside>

        <section className="map-panel" aria-label="Mapa de corredores de escape">
          <MapView
            origin={origin}
            showOrigin={hasOrigin}
            viewMode={viewMode}
            routes={data?.routes ?? []}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onOriginChange={handleOriginChange}
          />

          <Legend />

          {selectedRoute && (
            <div className="map-readout">
              <span>Corredor seleccionado</span>
              <strong>{selectedRoute.label}</strong>
              <small>
                {selectedRoute.escape_time_min} min · QuietScore{' '}
                {selectedRoute.quiet_score} · Escape Point en{' '}
                {selectedRoute.escape_point.name}
              </small>
            </div>
          )}

          {loading && (
            <div className="map-status">
              <span className="spinner spinner--light" />
              Calculando corredores…
            </div>
          )}
        </section>
      </main>

      {toast && (
        <div className="toast" role="status">
          <span>{toast}</span>
          <button type="button" onClick={() => setToast(null)} aria-label="Cerrar aviso">
            ×
          </button>
        </div>
      )}

      <SettingsModal
        open={settingsOpen}
        profile={profile}
        onSave={handleSettingsSave}
        onClose={() => setSettingsOpen(false)}
      />

      <InfoModal open={infoOpen} onClose={() => setInfoOpen(false)} />
    </div>
  );
}
