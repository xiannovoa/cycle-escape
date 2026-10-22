# AGENTS.md — Reglas de colaboración

Este documento es la **fuente de verdad** para las personas y los agentes de IA que
trabajan en Cycle Escape. Si una instrucción contradice este documento, pregunta antes de
improvisar.

Contexto de producto, arquitectura y puesta en marcha: [`README.md`](README.md).
Contrato de API: [`docs/api-contract.md`](docs/api-contract.md).
Normalización de datos de tráfico: [`docs/data-normalization.md`](docs/data-normalization.md).
Guion de demo: [`docs/demo-script.md`](docs/demo-script.md).

---

## 1. Objetivo del proyecto

Cycle Escape ayuda a un ciclista de carretera que está en una ciudad desconocida a decidir
**por qué dirección salir** hacia carreteras tranquilas, sin necesidad de tener un destino.

El MVP se demuestra en Santiago de Compostela. La arquitectura no debe quedar hardcodeada
a esa ciudad más allá de los datos de ejemplo y la configuración de la demo.

Es un hackathon de **un día** (Hackathon de la ETSE 2026). La prioridad es una demo clara y
fiable, no una arquitectura perfecta.

---

## 2. Reglas de oro del producto

1. **No es un planificador A → B.** No añadir destinos, navegación giro a giro ni búsqueda
   de direcciones.
2. **Escape Point ≠ límite de la ciudad ≠ primera carretera vacía.** Debe existir una red
   sostenida de bajo estrés después del punto.
3. **Nunca llamar "Safety Score"** a Road Stress. Es una estimación de estrés y exposición
   al tráfico.
4. **Sin medición no significa tráfico cero.** Los tramos sin aforo se estiman con OSM y se
   marcan como estimados, con menor confianza.
5. **OpenStreetMap es siempre el grafo base** de routing y geometría.
6. **La demo debe funcionar sin backend terminado**, usando el mock con la misma forma que
   el contrato.

---

## 3. Propiedad del código

Cada persona (y su agente) trabaja solo en su ámbito. No se refactoriza ni se reescribe el
trabajo de otra persona.

| Área | Responsable | Rutas |
|---|---|---|
| Frontend | Javi | `frontend/` |
| Datos de tráfico | Eva | `data/`, scripts de normalización, GeoJSON, metadatos |
| OSM / routing / API | Xián | `backend/` |
| Documentación compartida | Equipo | `README.md`, `AGENTS.md`, `docs/` |

Reglas:

- No cambies código de otra área "porque sería más limpio".
- No renombres ni elimines ficheros ajenos sin hablarlo antes.
- Si necesitas un cambio en otra área, pídelo o abre un issue; no lo hagas por tu cuenta.
- Los documentos compartidos se actualizan con PR y revisión, igual que el código.

---

## 4. Contrato compartido

### Campos congelados

No renombrar ni cambiar el significado de estos campos sin coordinarlo con los tres
desarrolladores:

`imd`, `heavy_pct`, `traffic_source`, `traffic_year`, `traffic_confidence`,
`road_stress`, `quiet_score`, `escape_point`, `escape_time_min`,
`distance_to_escape_km`.

Cualquier campo nuevo debe ser **aditivo** y opcional siempre que sea posible, para no
romper al consumidor.

### Convenciones del contrato

- JSON en `snake_case`.
- Geometrías en **GeoJSON**: coordenadas `[lon, lat]`.
- Leaflet usa `[lat, lng]`: la conversión se hace en un único helper del frontend.
- `road_stress` y `quiet_score`: escala 0–100.
  - `road_stress` alto = peor.
  - `quiet_score` alto = mejor (más tranquilo).
- `traffic_source`: `xunta` | `mitma` | `osm_estimate`.
- `traffic_confidence`: `high` | `medium` | `low`.
- `traffic_year` e `imd` pueden ser `null` si no hay medición. **Nunca usar 0 como
  sustituto de "sin datos".**
- Las distancias van en kilómetros y los tiempos en minutos, tal como indican los nombres.
- El contrato se versiona con `schema_version` en la respuesta.

El contrato completo, con ejemplos y decisiones cerradas, está en
[`docs/api-contract.md`](docs/api-contract.md). La v0.1 está implementada en
`backend/app/models.py` y cubierta por tests; los cambios deben ser aditivos y, a ser
posible, opcionales para no romper a los consumidores.

---

## 5. Frontend

Stack: **React + Vite + TypeScript + Leaflet / React-Leaflet**. Sin Next.js, sin Redux,
sin router si no hace falta.

Reglas:

- El frontend debe funcionar con datos mock desde el principio.
- `frontend/src/api.ts` intenta el backend y cae al mock si falla o no está disponible.
- Los datos mock viven en el repositorio y respetan el contrato.
- Un único helper convierte GeoJSON `[lon, lat]` a Leaflet `[lat, lng]`.
- El color de cada segmento se deriva de `road_stress` con una función centralizada; no se
  repiten umbrales por componentes.
- El Escape Point debe ser visualmente inequívoco (marcador destacado, no un punto más).
- Mostrar siempre que sea posible: fuente, año y confianza del tráfico.
- Mostrar la atribución **© OpenStreetMap contributors** en el mapa.
- La interfaz debe ser usable en portátil de demo (1280×720 como mínimo razonable).
- No introducir dependencias nuevas sin justificarlo; el tiempo es limitado.
- No hardcodear Santiago en la lógica de la interfaz: la ciudad es un dato, no una
  constante.

Estructura de referencia (puede ajustarse sin romper el contrato):

```text
frontend/src/
├── api/          # cliente HTTP + fallback mock
├── components/   # mapa, panel, tarjetas, leyenda
├── data/         # respuesta mock
├── hooks/        # estado de búsqueda y selección
├── types/        # tipos del contrato
└── utils/        # colores, formato, conversión de coordenadas
```

---

## 6. Backend

- FastAPI + Pydantic para el contrato.
- OSMnx/NetworkX para el grafo y el routing; GeoPandas/Shapely para el matching.
- El grafo descargado se cachea en local; no se versiona.
- El scoring debe ser determinista y explicable.
- Los segmentos sin aforo llevan `traffic_source: "osm_estimate"`, `imd: null` y confianza
  baja o media según la calidad de los atributos OSM.
- Habilitar CORS para el servidor de desarrollo del frontend o acordar un proxy `/api`.
- Devolver errores con un formato estable y códigos HTTP correctos.
- No incluir secretos ni rutas absolutas de la máquina en la API.

---

## 7. Datos

- Xunta de Galicia: aforos de 2016–2025 (edición 2025); el año real se conserva por tramo.
- MITMA: dataset principalmente de 2022; incluye N-550 y N-525 alrededor de Santiago.
- Los conjuntos pequeños de `data/raw/` **sí se versionan** (ver `data/raw/README.md`);
  los artefactos derivados de `data/processed/` **no se commitean**.
- No se inventan mediciones. Un valor estimado se etiqueta como estimado.
- Mantener trazabilidad: fuente, año y método de estimación.
- La normalización, la confianza y el matching se documentan en `docs/data-normalization.md`.

---

## 8. Seguridad y secretos

- **Nunca** subir claves API, tokens, credenciales de OpenRouter ni ficheros `.env`.
- Solo se versiona `.env.example` con valores vacíos o de ejemplo.
- No añadir autenticación, cuentas, pagos ni base de datos: están fuera del MVP.
- No ejecutar comandos destructivos sobre datos o ramas compartidas sin confirmación.

---

## 9. Git y revisión

- `main` debe quedar siempre en estado demostrable.
- Trabajar en ramas cortas:
  - `feat/frontend-...`
  - `feat/routing-...`
  - `feat/data-...`
  - `docs/...`
  - `fix/...`
- Commits con Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`); descripción clara
  y en español o inglés, pero consistente.
- Integración mediante Pull Request a `main`, con al menos una revisión.
- No hacer force-push a `main`.
- No commitear `node_modules/`, `.venv/`, `data/processed/`, ficheros temporales ni secretos.
  Los datos pequeños de `data/raw/` sí se versionan (ver `data/raw/README.md`).
- Un PR debe tener un alcance pequeño y explicar qué cambia y cómo probarlo.
- Si un cambio afecta al contrato, se indica explícitamente en el PR y se avisa al equipo.

---

## 10. Entorno local

- Windows es el entorno principal de la demo; evitar scripts que solo funcionen en Unix.
- Node 20+ y npm (no se asume pnpm).
- Python 3.11+.
- Comandos de arranque en el [`README.md`](README.md).

---

## 11. Cómo debe trabajar un agente de IA

1. **Lee primero** `AGENTS.md`, `README.md` y el contrato antes de tocar código.
2. **Respeta el ámbito**: si la tarea es de frontend, no edites `backend/` ni `data/`.
3. **Haz cambios pequeños y revisables**; no refactorices lo que no se ha pedido.
4. **No renombres campos compartidos** ni cambies la forma de la respuesta.
5. **No inventes datos de tráfico** ni presentes estimaciones como mediciones.
6. **Pregunta** cuando la tarea sea ambigua o afecte a otra área.
7. **Verifica** que el frontend compila y que la demo funciona con el mock.
8. **Reporta** qué has cambiado, qué has probado y qué queda pendiente.
9. **No commitees** salvo que se pida explícitamente.
10. **No introduzcas** autenticación, bases de datos, telemetría ni dependencias pesadas.

---

## 12. Definition of Done

Para considerar una tarea terminada:

- El cambio está dentro del ámbito asignado.
- Compila / arranca sin errores.
- Respeta el contrato y los nombres de campo.
- El frontend sigue funcionando con el mock si el backend falla o no está disponible.
- No se han añadido secretos ni datos voluminosos.
- La demo se puede explicar en una frase.
- Si aplica, la documentación se ha actualizado.

### Checklist antes de la demo

- [ ] El frontend arranca con `npm run dev`.
- [ ] El mapa carga teselas y atribución.
- [ ] Se puede elegir un origen y lanzar la búsqueda.
- [ ] Se ven al menos tres corredores candidatos.
- [ ] La ruta recomendada está resaltada y el Escape Point es evidente.
- [ ] Los colores de estrés y la leyenda son coherentes.
- [ ] Se muestran Escape Time, distancia y QuietScore.
- [ ] Se muestran fuente, año y confianza de los datos.
- [ ] `GET /api/health` responde `ok` y la caché de grafo está precalentada.
- [ ] Se ha probado el modo live (`VITE_USE_MOCK=false`) y el fallback a mock.
- [ ] Hay captura o vídeo de respaldo por si falla la red.
- [ ] El guion de demo se ha ensayado al menos una vez.

---

## 13. Decisiones cerradas y pendientes

### Cerradas para v0.1

Implementadas y cubiertas por tests:

- **Endpoint final:** `POST /api/escape-routes`; diagnóstico en `GET /api/health`.
- **Umbrales de `traffic_confidence`:**
  - Xunta con año real ≤ 3 años respecto al actual → `high`.
  - Xunta más antiguo o sin año → `medium`.
  - MITMA (aforo de 2022 en el MVP) → `medium`.
  - `osm_estimate` → `low`.
  - Confianza agregada de ruta: `high` si `measured_share >= 0.75` y todos los tramos
    medidos son `high`; `low` si no hay ningún tramo medido; `medium` en el resto.
- **`quiet_score`:** se expone por ruta, calculado sobre la red posterior al Escape
  Point. El contrato de segmento expone `road_stress`, no `quiet_score` por tramo.
- **Número de candidatos:** 5 por defecto, máximo 7.
- **Etiquetas:** el backend compone `label` a partir de la dirección y del nombre del
  Escape Point. El frontend no recalcula el ranking.
- **Geocodificación:** en el cliente con Nominatim; el backend solo recibe coordenadas.
- **Prioridad:** `traffic_lambda` es continuo; `route_preference` se mantiene por
  compatibilidad con clientes antiguos.

### Pendientes

- Aplicar `surface_preference` como preferencia o filtro de coste en el routing.
- Unificar la política de confianza: el backend agrega con `measured_share >= 0.75` y
  todos los tramos `high`; el frontend puede elevar el nivel mostrado con un 30 % de
  aforo reciente (PR #7). Debe quedar una sola fuente de verdad.
- Desacoplar por completo la ciudad de demo y soportar varias cachés de grafo.
- Ampliar la cobertura de aforos y revisar los umbrales con ciclistas locales.
- Decidir si `quiet_score` se expone también por segmento.

Cuando se cierre una decisión, actualizar este documento y el contrato en el mismo PR.
