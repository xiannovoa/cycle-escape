# Normalización de datos de tráfico

Documentación del pipeline de datos (responsable: **Eva**). Cubre qué entra, qué sale,
cómo se normaliza y qué decisiones están cerradas. El contrato de API está en
[`api-contract.md`](api-contract.md); las reglas de equipo, en [`../AGENTS.md`](../AGENTS.md).

---

## 1. Entradas y salida

| Entrada | Fuente | Cobertura |
|---|---|---|
| `data/raw/xunta/AC-*.geojson` | Xunta de Galicia | 6 carreteras autonómicas, 22 tramos |
| `data/raw/mitma/mitma_santiago.geojson` | MITMA | N-550, N-525, N-634, 17 tramos |
| `data/raw/mitma/osm_*.json` | OpenStreetMap / Overpass | Geometría de apoyo para MITMA |

Salida versionada: **`data/raw/imd_santiago.geojson`** (39 tramos `LineString`,
EPSG:4326). Se regenera de forma reproducible con:

```bash
python data/build_imd_dataset.py
```

El script no modifica los ficheros de origen. No se versiona ningún artefacto en
`data/processed/`.

---

## 2. Esquema canónico (`backend/app/data_loader.py`)

El GeoJSON mantiene nombres en español; el cargador los traduce a los campos del
contrato, ya congelados:

| GeoJSON | Canónico | Tipo | Notas |
|---|---|---|---|
| `Estrada` | `road_ref` | str | Mayúsculas, sin espacios sobrantes |
| `geometry` | `geometry` | LineString | `[lon, lat]`, EPSG:4326 |
| `IMD` | `imd` | int \| null | Vehículos/día; **nunca 0 por falta de dato** |
| `Pct_pesados` | `heavy_pct` | float \| null | Porcentaje 0–100, no fracción |
| `Fuente` | `traffic_source` | str | `xunta` \| `mitma` \| `osm_estimate` |
| `Anio` | `traffic_year` | int \| null | Año real del aforo |
| — | `traffic_confidence` | str | `high` \| `medium` \| `low` (se calcula al cargar) |
| `PK_inicio` | `pk_start` | float \| null | Kilómetro de inicio |
| `PK_fin` | `pk_end` | float \| null | Kilómetro de fin |
| `Corredor` | `corridor` | str \| null | Nombre del tramo/corredor |

`Nivel` (`tranquila` < 2000, `moderada` 2000–4999, `alta` 5000–9999, `muy_alta` ≥ 10000)
se conserva en el GeoJSON como etiqueta para la interfaz.

### Correspondencia con las fuentes

| Canónico | Xunta | MITMA |
|---|---|---|
| `imd` | `IMD_2025` | `IMD` |
| `heavy_pct` | `P_porcenta` | `Pct_pesados` |
| `pk_start` / `pk_end` | `Pq_inicio` / `Pq_fin` | `PK_inicio` / `PK_fin` |
| `traffic_year` | `Anho_afo_u` | `Anio` |
| `corridor` | `Treito` | `Corredor` |

---

## 3. Año del aforo: edición ≠ observación

La capa de la Xunta se publica como **«IMD 2025»** (año de edición), pero el campo
`Anho_afo_u` indica el año real de cada observación:

| Carretera | Años reales presentes |
|---|---|
| AC-250 | 2025 |
| AC-261 | 2024 |
| AC-453 | 2022 |
| AC-543 | 2023 y 2025 |
| AC-841 | 2016 y 2019 |
| AC-960 | 2023 |

MITMA corresponde a **2022**. Por eso `Anio` no puede fijarse a 2025 para toda la
Xunta: se copia el año real de cada tramo y la confianza se ajusta en consecuencia.
`Fuente` identifica solo la fuente (`Xunta` / `MITMA`); el año va en su propio campo.

---

## 4. Confianza implementada

| Fuente | Regla | Nivel |
|---|---|---|
| Xunta | Año real ≤ 3 años respecto al actual | `high` |
| Xunta | Año real más antiguo o desconocido | `medium` |
| MITMA | Aforo de 2022 | `medium` |
| OSM (estimado por routing) | Sin medición oficial | `low` |

Un dato **medido** nunca se marca como `low`. Los umbrales están implementados en
`backend/app/data_loader.py` (`XUNTA_RECENT_YEARS = 3`) y cerrados en `AGENTS.md` §13.

La confianza agregada de una ruta se calcula en `backend/app/main.py` a partir de la
fracción de distancia con aforo medido:

| Nivel de ruta | Criterio |
|---|---|
| `high` | `measured_share >= 0.75` y todos los tramos medidos son `high` |
| `medium` | Hay algún tramo medido, pero no se cumple `high` |
| `low` | `measured_share == 0`: toda la ruta es `osm_estimate` |

---

## 5. Validación

`validate_traffic_records()` comprueba, por tramo:

- campos canónicos completos y `road_ref` no vacío;
- `LineString` con ≥ 2 coordenadas válidas y dentro de rango;
- `imd` > 0 en datos medidos; `heavy_pct` entre 0 y 100;
- `traffic_year` entre 1990 y el año actual + 1;
- `traffic_source` y `traffic_confidence` dentro del enum;
- coherencia: una estimación `osm_estimate` no puede llevar `imd` ni `traffic_year`;
- `pk_start < pk_end` y ausencia de duplicados `(road_ref, pk_start, pk_end)`.

Devuelve un `ValidationReport` con `errors` (invalidan la capa) y `warnings` (revisables).
Estado actual de la capa: **39 tramos, 0 errores, 0 avisos**.

---

## 6. Uso desde el backend

```python
from app.data_loader import load_traffic_segments, validate_traffic_records, load_traffic_records

report = validate_traffic_records(load_traffic_records())
report.raise_if_invalid()

segments = load_traffic_segments()  # GeoDataFrame EPSG:4326
# segments[["road_ref", "imd", "heavy_pct", "traffic_source",
#           "traffic_year", "traffic_confidence", "geometry"]]
```

`load_traffic_segments()` requiere `geopandas`; `load_traffic_records()` solo usa la
librería estándar y devuelve dicts con la geometría GeoJSON lista para
`shapely.geometry.shape`.

El matching está implementado en `backend/app/traffic_enrichment.py`:

1. filtrar por `road_ref` compatible con `ref` de OSM;
2. exigir una distancia geométrica ≤ 30 m;
3. no asociar por proximidad sin `ref`: hay calles urbanas pegadas a la N-550;
4. si varias observaciones compiten por una arista, gana la más cercana, luego la de
   mayor confianza, luego la más reciente y, por seguridad, la de mayor IMD.

Con la caché v2 de Santiago (11.208 nodos y 25.760 aristas), el matching asocia
**30 de los 39 tramos** a **1.281 aristas** y **170,9 km** (4,2 % de la red total). Las
aristas restantes se estiman con OSM y se marcan como `osm_estimate`.

---

## 7. Limitaciones y trabajo pendiente

- **N-550 sur** está ~20 % estirada: la geometría MITMA se generó cortando OSM por PK
  con dos puntos de calibración. Los tramos van por la carretera correcta, pero el
  buffer de 30 m puede no bastar en los extremos.
- **Hueco N-550 sur PK 68,62–69** (~460 m) sin dato. Recomendación: imputar 25.074
  (el vecino más alto) y marcarlo como imputado; pendiente de implementar en la
  geometría, porque hay que generarla desde OSM.
- **N-634 no es Lavacolla**: va hacia O Empalme/Teixeiro. Lavacolla se cubre en parte
  con la AC-250.
- **Cobertura parcial**: solo hay aforo para 9 carreteras. El resto de aristas se
  estiman desde atributos OSM en routing (`traffic_source: osm_estimate`), no aquí.
- **Datos versionados**: `data/raw/` se versiona por tamaño reducido; los artefactos
  derivados de `data/processed/` no. La regla está recogida en `AGENTS.md` §7, en el
  README y en `data/raw/README.md`.
- **Trabajo pendiente**: ampliar la cobertura de aforos, revisar el hueco de la N-550 sur
  y decidir si se imputa el valor vecino más alto. Cualquier imputación debe marcarse como
  tal y no presentarse como medición.
