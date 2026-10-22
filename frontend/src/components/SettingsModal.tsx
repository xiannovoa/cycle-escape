import { useEffect, useState } from 'react';
import { Controls } from './Controls';
import {
  normalizeProfile,
  profileToPrefs,
  type RiderProfile,
} from '../profile';

interface SettingsModalProps {
  open: boolean;
  profile: RiderProfile;
  onSave: (profile: RiderProfile) => void;
  onClose: () => void;
}

export function SettingsModal({ open, profile, onSave, onClose }: SettingsModalProps) {
  const [draft, setDraft] = useState<RiderProfile>(profile);

  useEffect(() => {
    if (open) setDraft(profile);
  }, [open, profile]);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="info-overlay" onClick={onClose}>
      <section
        className="info-modal settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="info-modal__head">
          <div>
            <span className="eyebrow">Configuración</span>
            <h2 id="settings-title">Tu perfil</h2>
          </div>
          <button
            type="button"
            className="info-modal__close"
            onClick={onClose}
            aria-label="Cerrar configuración"
            autoFocus
          >
            ×
          </button>
        </header>

        <div className="info-modal__body">
          <label className="field">
            <span>Nombre</span>
            <input
              type="text"
              value={draft.name}
              maxLength={40}
              autoComplete="name"
              onChange={(event) =>
                setDraft((current) => ({ ...current, name: event.target.value }))
              }
            />
          </label>

          <div className="settings-preferences">
            <h3>Preferencias de salida</h3>
            <Controls
              prefs={profileToPrefs(draft)}
              onChange={(nextPrefs) =>
                setDraft((current) => ({ ...current, ...nextPrefs }))
              }
            />
          </div>

          <div className="settings-actions">
            <button type="button" className="settings-cancel" onClick={onClose}>
              Cancelar
            </button>
            <button
              type="button"
              className="settings-save"
              onClick={() => onSave(normalizeProfile(draft))}
            >
              Guardar cambios
            </button>
          </div>

          <p className="settings-note">
            Tus preferencias se guardan solo en este dispositivo.
          </p>
        </div>
      </section>
    </div>
  );
}
