import { useEffect } from 'react';

interface InfoModalProps {
  open: boolean;
  onClose: () => void;
}

export function InfoModal({ open, onClose }: InfoModalProps) {
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
        className="info-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="info-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="info-modal__head">
          <div>
            <span className="eyebrow">Información</span>
            <h2 id="info-title">Datos y confianza</h2>
          </div>
          <button
            type="button"
            className="info-modal__close"
            onClick={onClose}
            aria-label="Cerrar información"
            autoFocus
          >
            ×
          </button>
        </header>

        <div className="info-modal__body">
          <article>
            <h3>¿Qué es la confianza?</h3>
            <p>
              Indica cuánto respaldo tienen los datos de tráfico de un corredor. No es una
              medida de seguridad: una confianza alta no garantiza una carretera segura.
            </p>
            <ul>
              <li>
                <strong>Alta:</strong> la mayor parte del trazado tiene aforo oficial
                reciente y bien emparejado.
              </li>
              <li>
                <strong>Media:</strong> cobertura parcial, datos de varios años o un
                emparejamiento menos preciso.
              </li>
              <li>
                <strong>Baja:</strong> predominan tramos sin aforo, estimados a partir de
                atributos de OpenStreetMap.
              </li>
            </ul>
          </article>

          <article>
            <h3>¿Qué es OSM?</h3>
            <p>
              <strong>OpenStreetMap (OSM)</strong> es un mapa colaborativo y abierto. Es la
              base de la red viaria y de los atributos que usamos para estimar el estrés
              cuando no existe un aforo oficial.
            </p>
            <p>
              Un tramo marcado como <strong>OSM estimado</strong> no significa que tenga
              tráfico cero: significa que no hay una medición disponible y lo aproximamos
              con atributos como el tipo de vía, los carriles o la superficie.
            </p>
          </article>

          <p className="info-modal__note">
            El Road Stress es una estimación de estrés viario y exposición al tráfico, no
            un <em>safety score</em>.
          </p>
        </div>
      </section>
    </div>
  );
}
