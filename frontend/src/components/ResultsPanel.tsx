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

interface RouteTag {
  key: string;
  label: string;
}

const GOOD_BALANCE_SCORE = 70;

export function ResultsPanel({ routes, selectedId, onSelect }: ResultsPanelProps) {
  const recommended = routes.find((route) => route.is_recommended) ?? routes[0];
  const minTime = Math.min(...routes.map((route) => route.escape_time_min));
  const maxTime = Math.max(...routes.map((route) => route.escape_time_min));

  function timeScore(route: EscapeRoute): number {
    if (maxTime === minTime) return 100;
    return (100 * (maxTime - route.escape_time_min)) / (maxTime - minTime);
  }

  function balanceScore(route: EscapeRoute): number {
    return route.quiet_score * 0.6 + timeScore(route) * 0.4;
  }

  const fastest = [...routes].sort((a, b) => a.escape_time_min - b.escape_time_min)[0];
  const quietest = [...routes].sort((a, b) => b.quiet_score - a.quiet_score)[0];
  const lowestTraffic = [...routes].sort(
    (a, b) => a.avg_road_stress - b.avg_road_stress,
  )[0];
  const bestBalance = [...routes].sort((a, b) => balanceScore(b) - balanceScore(a))[0];
  const recommendedBalance = recommended ? balanceScore(recommended) : 0;

  const tags = new Map<string, RouteTag[]>();
  const usedLabels = new Set<string>();

  function addTag(route: EscapeRoute | undefined, key: string, label: string) {
    if (!route || usedLabels.has(label)) return;
    const current = tags.get(route.id) ?? [];
    if (!route.is_recommended && current.length >= 1) return;
    tags.set(route.id, [...current, { key, label }]);
    usedLabels.add(label);
  }

  addTag(fastest, 'fast', 'Más rápida');
  addTag(quietest, 'quiet', 'Más tranquila');
  addTag(lowestTraffic, 'traffic', 'Menor tráfico');

  if (bestBalance) {
    const score = balanceScore(bestBalance);
    const isGood =
      bestBalance.is_recommended ||
      (score >= GOOD_BALANCE_SCORE && score >= recommendedBalance - 10);
    if (isGood) addTag(bestBalance, 'balance', 'Mejor balance');
  }

  routes.forEach((route) => {
    if (!route.is_recommended && !tags.has(route.id)) {
      tags.set(route.id, [{ key: 'alternative', label: 'Alternativa' }]);
    }
  });

  function tagsFor(route: EscapeRoute): RouteTag[] {
    return tags.get(route.id) ?? [];
  }

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
          Sin aforo medido: baja. Cobertura del 1–2%: media. Cobertura superior al 2%:
          alta.
        </p>
      </details>

      <div className="route-list">
        {routes.map((route) => {
          const isSelected = route.id === selectedId;
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

              <div className="route-tags">
                {tagsFor(route).map((tag) => (
                  <span key={tag.key} className={`route-tag route-tag--${tag.key}`}>
                    {tag.label}
                  </span>
                ))}
              </div>

              <div className="route-card__meta">
                {route.is_recommended && <span className="rec-badge">Recomendada</span>}
                <span className="traffic-meta">
                  {route.traffic_summary.sources.map(sourceLabel).join(' · ')} · {years}
                </span>
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
