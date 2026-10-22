import type { SearchPreferences } from '../types';

interface Option {
  label: string;
  value: string;
}

interface SegmentedProps {
  ariaLabel: string;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
}

function Segmented({ ariaLabel, options, value, onChange }: SegmentedProps) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? 'is-active' : ''}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

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
          <span>Aversión al tráfico</span>
          <strong>
            {prefs.trafficAversion <= 0.3
              ? 'Baja'
              : prefs.trafficAversion >= 0.75
                ? 'Alta'
                : 'Media'}
          </strong>
        </div>
        <Segmented
          ariaLabel="Aversión al tráfico"
          value={String(prefs.trafficAversion)}
          options={[
            { label: 'Baja', value: '0.2' },
            { label: 'Media', value: '0.5' },
            { label: 'Alta', value: '0.85' },
          ]}
          onChange={(value) => setField('trafficAversion', Number(value))}
        />
      </div>

      <div className="control">
        <div className="control__label">
          <span>Prioridad</span>
        </div>
        <input
          className="range range--lambda"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={prefs.trafficLambda}
          aria-label="Prioridad: de salida directa a menor tráfico"
          title="0 = salida directa · 1 = menor tráfico"
          onChange={(event) => setField('trafficLambda', Number(event.target.value))}
        />
        <div className="range__scale range__scale--lambda">
          <span>Salida directa</span>
          <span>Equilibrada</span>
          <span>Menor tráfico</span>
        </div>
      </div>
    </div>
  );
}
