import { useState } from 'react';
import type { FormEvent } from 'react';
import { Controls } from './Controls';
import {
  DEFAULT_PROFILE,
  normalizeProfile,
  profileToPrefs,
  type RiderProfile,
} from '../profile';

interface OnboardingProps {
  initialProfile?: RiderProfile;
  onComplete: (profile: RiderProfile) => void;
}

export function Onboarding({ initialProfile = DEFAULT_PROFILE, onComplete }: OnboardingProps) {
  const [draft, setDraft] = useState<RiderProfile>(initialProfile);
  const prefs = profileToPrefs(draft);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onComplete(normalizeProfile(draft));
  }

  return (
    <div className="onboarding">
      <form className="onboarding__card" onSubmit={handleSubmit}>
        <div className="onboarding__brand">
          <span className="onboarding__mark" aria-hidden="true">
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
          <div>
            <strong>Cyclout</strong>
            <span>Tu perfil de ciclista</span>
          </div>
        </div>

        <span className="eyebrow">Antes de salir</span>
        <h1>Cuéntanos cómo pedaleas</h1>
        <p className="onboarding__intro">
          Guardaremos tus preferencias en este dispositivo para no preguntártelas en cada
          salida. Podrás cambiarlas cuando quieras desde ajustes.
        </p>

        <label className="field">
          <span>¿Cómo te llamas?</span>
          <input
            type="text"
            value={draft.name}
            maxLength={40}
            placeholder="Tu nombre"
            autoComplete="name"
            onChange={(event) =>
              setDraft((current) => ({ ...current, name: event.target.value }))
            }
          />
        </label>

        <div className="onboarding__preferences">
          <span className="eyebrow">Preferencias</span>
          <Controls
            prefs={prefs}
            onChange={(nextPrefs) =>
              setDraft((current) => ({ ...current, ...nextPrefs }))
            }
          />
        </div>

        <button type="submit" className="onboarding__submit">
          Empezar a explorar
          <span aria-hidden="true">→</span>
        </button>

        <p className="onboarding__note">
          Perfil local: no creamos cuentas ni guardamos contraseñas.
        </p>
      </form>
    </div>
  );
}
