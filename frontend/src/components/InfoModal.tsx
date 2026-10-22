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
            <h2 id="info-title">Datos y métricas</h2>
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
            <h3>¿Qué es el Escape Point?</h3>
            <p>
              Es el primer punto desde el que los siguientes 5 km mantienen un
              QuietScore medio de al menos 80 y un 80% del trazado con estrés igual o
              inferior a 30, fuera de una zona urbana densa. Si un corredor no cumple
              estos criterios, no se muestra como salida.
            </p>
          </article>

          <article>
            <h3>¿Qué es la preferencia de salida?</h3>
            <p>
              Un único control de <strong>más rápido</strong> a <strong>menor
              tráfico</strong>. A la izquierda prima el tiempo y se tolera más tráfico; a
              la derecha prima el QuietScore y se evita más el tráfico. Ajusta a la vez la
              prioridad y la aversión al tráfico.
            </p>
          </article>

          <article>
            <h3>¿Qué es el QuietScore?</h3>
            <p>
              Es una puntuación de 0 a 100 derivada del Road Stress. Un valor alto indica
              un entorno más tranquilo. Se calcula sobre la red posterior al Escape Point
              y no es una medida de seguridad.
            </p>
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
