import type { EscapeRoute } from '../types';
import {
  confidenceLabel,
  directionArrow,
  formatKm,
  formatMinutes,
  quietScoreColor,
  sourceLabel,
} from '../utils';

interface ResultsPanelProps {
  routes: EscapeRoute[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ResultsPanel({ routes, selectedId, onSelect }: ResultsPanelProps) {
  return (
    <section className="results" aria-label="Corredores de escape candidatos">
      <div className="results__head">
        <div>
          <span className="eyebrow">Resultados</span>
          <h2>Corredores de escape</h2>
        </div>
        <span className="results__count">{routes.length}</span>
      </div>
      <p className="results__hint">Toca un corredor para verlo en el mapa.</p>

      <details className="confidence-note">
        <summary>¿Cómo se calcula la confianza?</summary>
        <p>
          Combina la cobertura de aforo reciente con la calidad de los datos OSM. Alta:
          al menos un 30% del trazado con aforo reciente. Media: cobertura parcial, datos
          antiguos o buena base OSM. Baja: sin aforo y con información OSM escasa.
        </p>
      </details>

      <div className="route-list">
        {routes.map((route) => {
          const isSelected = route.id === selectedId;
          const measured = Math.round(route.traffic_summary.measured_share * 100);
          const years = route.traffic_summary.years.length
            ? route.traffic_summary.years.join(', ')
            : 'sin año';

          return (
            <div
              key={route.id}
              role="button"
              tabIndex={0}
              aria-pressed={isSelected}
              className={[
                'route-card',
                `confidence--${route.traffic_summary.confidence}`,
                isSelected ? 'is-selected' : '',
                route.is_recommended ? 'is-recommended' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => onSelect(route.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(route.id);
                }
              }}
            >
              <div className="route-card__head">
                <span className={`direction direction--${route.direction.toLowerCase()}`}>
                  {directionArrow(route.direction)}
                </span>
                <span className="route-card__title">
                  <strong>{route.label}</strong>
                  <small>Escape Point · {route.escape_point.name}</small>
                </span>
                <span
                  className={`confidence confidence--header confidence--${route.traffic_summary.confidence}`}
                >
                  <i />
                  Confianza {confidenceLabel(route.traffic_summary.confidence)}
                </span>
              </div>

              <div className="metrics">
                <div className="metric">
                  <strong>
                    {formatMinutes(route.escape_time_min)}
                    <em>min</em>
                  </strong>
                  <span>Escape Time</span>
                </div>
                <div className="metric">
                  <strong>
                    {formatKm(route.distance_to_escape_km)}
                    <em>km</em>
                  </strong>
                  <span>hasta salir</span>
                </div>
                <div className="metric">
                  <strong style={{ color: quietScoreColor(route.quiet_score) }}>
                    {route.quiet_score}
                    <em>/100</em>
                  </strong>
                  <span>QuietScore</span>
                </div>
              </div>

              <div className="route-card__meta">
                {route.is_recommended && <span className="rec-badge">Recomendada</span>}
                <span className="traffic-meta">
                  {route.traffic_summary.sources.map(sourceLabel).join(' · ')} · {years}
                </span>
              </div>

              <div className="measured">
                <span className="measured__track">
                  <span style={{ width: `${measured}%` }} />
                </span>
                <small>{measured}% del trazado con aforo</small>
              </div>

              {route.warnings.length > 0 && (
                <p className="route-card__warning">{route.warnings[0]}</p>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
