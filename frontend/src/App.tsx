import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { searchEscapeRoutes } from './api';
import { Controls } from './components/Controls';
import { InfoModal } from './components/InfoModal';
import { Legend } from './components/Legend';
import { MapView } from './components/MapView';
import { ResultsPanel } from './components/ResultsPanel';
import { reverseGeocode, searchStreet } from './geocode';
import type { EscapeResponse, LatLon, SearchPreferences } from './types';

const DEFAULT_ORIGIN: LatLon = { lat: 42.8782, lon: -8.5448 };

const DEFAULT_PREFS: SearchPreferences = {
  avgSpeedKmh: 22,
  trafficAversion: 0.5,
  trafficLambda: 0.5,
  surfacePreference: 'asphalt',
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
  const [originName, setOriginName] = useState('Santiago de Compostela');
  const [originLocality, setOriginLocality] = useState('Santiago de Compostela');
  const [geocoding, setGeocoding] = useState(false);
  const [streetQuery, setStreetQuery] = useState('');
  const [streetSearching, setStreetSearching] = useState(false);
  const [streetError, setStreetError] = useState<string | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);

  const requestId = useRef(0);
  const geocodeRequestId = useRef(0);
  const skipNextGeocode = useRef(false);

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
      setSelectedId(null);
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

  function clearResults() {
    requestId.current += 1;
    setLoading(false);
    setData(null);
    setSource(null);
    setSelectedId(null);
    setNotice(null);
    setError(null);
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
    setGeocoding(true);
    setStreetError(null);
    clearResults();
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
    setOriginName(result.name);
    setOriginLocality(result.locality);
    setGeocoding(false);
    setStreetQuery('');
    clearResults();
  }

  function handlePrefsChange(nextPrefs: SearchPreferences) {
    setPrefs(nextPrefs);
  }

  const selectedRoute = data?.routes.find((route) => route.id === selectedId) ?? null;
  const originHint = geocoding
    ? 'OpenStreetMap'
    : `${originLocality && originLocality !== originName ? `${originLocality} · ` : ''}Toca el mapa para cambiar el origen`;
  const sourceLabelText =
    source === 'live'
      ? 'Datos en vivo'
      : source === 'mock'
        ? 'Datos de ejemplo'
        : 'Sin buscar';

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
          <button
            type="button"
            className="info-button"
            onClick={() => setInfoOpen(true)}
            aria-haspopup="dialog"
          >
            <span className="info-button__icon" aria-hidden="true">
              i
            </span>
            Información
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
              title={`${origin.lat.toFixed(4)}, ${origin.lon.toFixed(4)}`}
            >
              {geocoding ? 'Buscando calle…' : originName}
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
            <small>{originHint}</small>
            {streetError && <small className="origin-error">{streetError}</small>}
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
              <strong>Elige tu salida</strong>
              <p>
                Ajusta el origen y las preferencias, y pulsa “Buscar salidas” para
                explorar la red que te rodea.
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

      <InfoModal open={infoOpen} onClose={() => setInfoOpen(false)} />
    </div>
  );
}
