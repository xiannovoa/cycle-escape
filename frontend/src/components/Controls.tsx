import type { SearchPreferences } from '../types';
import { trafficAversionForPreference } from '../profile';

interface ControlsProps {
  prefs: SearchPreferences;
  onChange: (prefs: SearchPreferences) => void;
}

export function Controls({ prefs, onChange }: ControlsProps) {
  function setField<K extends keyof SearchPreferences>(
    key: K,
    value: SearchPreferences[K],
  ) {
    onChange({ ...prefs, [key]: value });
  }

  function setPreference(value: number) {
    onChange({
      ...prefs,
      trafficLambda: value,
      trafficAversion: trafficAversionForPreference(value),
    });
  }

  return (
    <div className="controls">
      <div className="control">
        <div className="control__label">
          <span>Velocidad media</span>
          <strong>{prefs.avgSpeedKmh} km/h</strong>
        </div>
        <input
          className="range"
          type="range"
          min={10}
          max={40}
          step={1}
          value={prefs.avgSpeedKmh}
          aria-label="Velocidad media en kilómetros por hora"
          onChange={(event) => setField('avgSpeedKmh', Number(event.target.value))}
        />
        <div className="range__scale">
          <span>10</span>
          <span>25</span>
          <span>40</span>
        </div>
      </div>

      <div className="control">
        <div className="control__label">
          <span>Preferencia de salida</span>
        </div>
        <input
          className="range range--lambda"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={prefs.trafficLambda}
          aria-label="Preferencia de salida: de más rápido a menor tráfico"
          title="0 = más rápido · 1 = menor tráfico"
          onChange={(event) => setPreference(Number(event.target.value))}
        />
        <div className="range__scale range__scale--lambda">
          <span>Más rápido</span>
          <span>Equilibrada</span>
          <span>Menor tráfico</span>
        </div>
        <small className="control__hint">
          Ajusta a la vez la prioridad y la aversión al tráfico.
        </small>
      </div>
    </div>
  );
}
