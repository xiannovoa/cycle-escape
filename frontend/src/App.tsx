import { useEffect, useRef, useState } from 'react';
import { searchEscapeRoutes } from './api';
import { Controls } from './components/Controls';
import { Legend } from './components/Legend';
import { MapView } from './components/MapView';
import { ResultsPanel } from './components/ResultsPanel';
import type { EscapeResponse, LatLon, SearchPreferences } from './types';

const DEFAULT_ORIGIN: LatLon = { lat: 42.8782, lon: -8.5448 };

const DEFAULT_PREFS: SearchPreferences = {
  avgSpeedKmh: 22,
  trafficAversion: 0.5,
  surfacePreference: 'asphalt',
  routePreference: 'balanced',
};

export default function App() {
  const [origin, setOrigin] = useState<LatLon>(DEFAULT_ORIGIN);
  const [prefs, setPrefs] = useState<SearchPreferences>(DEFAULT_PREFS);
  const [data, setData] = useState<EscapeResponse | null>(null);
  const [source, setSource] = useState<'live' | 'mock' | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const didInit = useRef(false);
  const requestId = useRef(0);

  async function runSearch(nextOrigin: LatLon, nextPrefs: SearchPreferences) {
    const currentRequest = requestId.current + 1;
    requestId.current = currentRequest;
    setLoading(true);
    setError(null);

    try {
      const result = await searchEscapeRoutes(nextOrigin, nextPrefs);
      if (currentRequest !== requestId.current) return;

      setData(result.response);
      setSource(result.source);
      setNotice(result.warning ?? null);
      setSelectedId(
        result.response.recommended_route_id || result.response.routes[0]?.id || null,
      );
    } catch (searchError) {
      if (currentRequest !== requestId.current) return;
      console.error(searchError);
      setError('No se pudieron calcular los corredores. Inténtalo de nuevo.');
    } finally {
      if (currentRequest === requestId.current) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    void runSearch(DEFAULT_ORIGIN, DEFAULT_PREFS);
  }, []);

  function handleOriginChange(nextOrigin: LatLon) {
    setOrigin(nextOrigin);
    void runSearch(nextOrigin, prefs);
  }

  function handlePrefsChange(nextPrefs: SearchPreferences) {
    setPrefs(nextPrefs);
  }

  const selectedRoute = data?.routes.find((route) => route.id === selectedId) ?? null;
  const sourceLabelText =
    source === 'live'
      ? 'Datos en vivo'
      : source === 'mock'
        ? 'Datos de ejemplo'
        : 'Conectando';

  return (
    <div className="app">
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
            <h1>Cycle Escape</h1>
            <p>Sal de la ciudad. Encuentra carreteras tranquilas.</p>
          </div>
        </div>

        <div className="topbar__meta">
          <span className={`source-badge source-badge--${source ?? 'loading'}`}>
            <i />
            {sourceLabelText}
          </span>
          <span className="city-badge">Santiago de Compostela</span>
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
            <strong className="origin-card__coords">
              {origin.lat.toFixed(4)}, {origin.lon.toFixed(4)}
            </strong>
            <small>Haz clic en el mapa para mover el punto de salida.</small>
          </section>

          <div className="section-heading">
            <span className="eyebrow">Preferencias</span>
            <h2>¿Cómo quieres salir?</h2>
          </div>

          <Controls prefs={prefs} onChange={handlePrefsChange} />

          <button
            type="button"
            className="search-button"
            disabled={loading}
            onClick={() => void runSearch(origin, prefs)}
          >
            {loading ? (
              <>
                <span className="spinner spinner--light" />
                Calculando salidas…
              </>
            ) : (
              <>
                Buscar salidas
                <span aria-hidden="true">→</span>
              </>
            )}
          </button>

          {notice && <div className="notice">{notice}</div>}
          {error && <div className="notice notice--error">{error}</div>}

          {loading && !data && (
            <div className="skeleton-list" aria-hidden="true">
              <div className="skeleton-card" />
              <div className="skeleton-card" />
              <div className="skeleton-card" />
            </div>
          )}

          {!loading && !data && !error && (
            <div className="empty-state">
              <strong>Sin corredores todavía</strong>
              <p>Pulsa “Buscar salidas” para explorar la red que rodea el origen.</p>
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
    </div>
  );
}
