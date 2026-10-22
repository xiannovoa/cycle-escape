import { STRESS_BANDS } from '../utils';

export function Legend() {
  return (
    <div className="legend" aria-label="Leyenda de estrés viario">
      <span className="legend__title">Estrés viario</span>
      <div className="legend__items">
        {STRESS_BANDS.map((band) => (
          <span key={band.label} className="legend__item">
            <i style={{ background: band.color }} />
            {band.label}
          </span>
        ))}
      </div>
      <span className="legend__foot">Verde = más tranquilo · rojo = más estrés</span>
    </div>
  );
}
