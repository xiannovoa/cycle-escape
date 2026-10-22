# Datos en crudo (`data/raw`)

Conxuntos de datos de entrada do proxecto. Son ficheiros pequenos (~2,8 MB en total),
por iso se versionan no repositorio: calquera persoa do equipo que clone o repo
ten todo o necesario para traballar sen pasos previos.

> Os artefactos derivados van en `data/processed/` e **non** se versionan
> (ver `.gitignore`). Pódense rexenerar a partir destes ficheiros.

## Estrutura

```
data/raw/
├── imd_santiago.geojson           Capa IMD unificada (Xunta + MITMA), 39 tramos
├── mitma/
│   ├── mitma_santiago.geojson     IMD dos tramos MITMA (área de Santiago)
│   ├── N-525.geojson              Subconxunto: estrada N-525
│   ├── N-550.geojson              Subconxunto: estrada N-550
│   ├── N-634.geojson              Subconxunto: estrada N-634
│   ├── osm_N-525.json             Export OSM (Overpass) da N-525
│   ├── osm_N-550.json             Export OSM (Overpass) da N-550
│   └── osm_N-634.json             Export OSM (Overpass) da N-634
└── xunta/
    ├── AC-250.geojson             Rede autonómica: AC-250
    ├── AC-261.geojson             Rede autonómica: AC-261
    ├── AC-453.geojson             Rede autonómica: AC-453
    ├── AC-543.geojson             Rede autonómica: AC-543
    ├── AC-841.geojson             Rede autonómica: AC-841
    └── AC-960.geojson             Rede autonómica: AC-960
```

## `imd_santiago.geojson` — capa IMD unificada

Capa única (`FeatureCollection`, EPSG:4326) con **39 tramos** `LineString` que combina os
aforos da **Xunta** (observacións de 2016–2025) e de **MITMA** (2022). É o ficheiro de
entrada para o matching co grafo de OSM no backend. Xérase de forma reproducible con
`python data/build_imd_dataset.py` a partir das fontes de `xunta/` e `mitma/`.

| Campo | Descrición |
|---|---|
| `Estrada` | Código da estrada (ex. `N-550`, `AC-250`) |
| `Corredor` | Nome do tramo ou corredor |
| `PK_inicio`, `PK_fin` | Punto quilométrico de inicio e fin |
| `IMD` | Intensidade media diaria (vehículos/día) |
| `Pct_pesados` | Porcentaxe de vehículos pesados |
| `Anio` | Ano real do aforo (MITMA 2022; Xunta 2016–2025) |
| `Fuente` | `Xunta` ou `MITMA` |
| `Nivel` | `tranquila` (< 2000), `moderada` (2000–4999), `alta` (5000–9999), `muy_alta` (≥ 10000) |

Reparto: 6 tramos tranquilos, 13 moderados, 3 altos e 17 moi altos.

> A confianza (`traffic_confidence`) non vai no GeoJSON: calcúlaa
> `backend/app/data_loader.py` a partir da fonte e do ano real. Esquema canónico,
> regras de confianza, validación e limitacións:
> [`docs/data-normalization.md`](../../docs/data-normalization.md).
> Contexto orixinal dos datos: [`docs/prompt-contexto-datos.md`](../../docs/prompt-contexto-datos.md).

## `mitma/` — intensidades de tráfico

Fonte: **MITMA mapatrafico** (Ministerio de Transportes y Movilidad Sostenible),
datos de IMD (intensidade media diaria) do ano **2022**.

Cada `Feature` é un tramo de estrada con xeometría `LineString` e estas
propiedades:

| Campo | Descrición |
|---|---|
| `Estrada` | Código da estrada (ex. `N-550`) |
| `Corredor` | Nome do corredor / subtramo |
| `Tipo` | Tipo de vía (ex. `Carretera convencional`) |
| `PK_inicio`, `PK_fin` | Punto quilométrico de inicio e fin |
| `Longitud_km` | Lonxitude do tramo en km |
| `IMD` | Intensidade media diaria (total de vehículos/día) |
| `IMD_ligeros` | IMD de vehículos lixeiros |
| `IMD_pesados` | IMD de vehículos pesados |
| `Pct_pesados` | Porcentaxe de pesados sobre o total |
| `vhkm_total` | Vehículos·km totais |
| `Anio` | Ano do dato |
| `Fuente` | Orixe do dato |

Os ficheiros `N-*.geojson` son a mesma información filtrada por estrada, para
evitar cargar o conxunto completo en cada proba.

## `xunta/` — rede viaria autonómica

Fonte: **Xunta de Galicia**, xeometría da rede de estradas autonómicas
(ficheiros `AC-*.geojson`, formato `FeatureCollection`).

## `osm_*.json` — OpenStreetMap

Exportacións de **OpenStreetMap** obtidas vía API Overpass, por estrada.

> © OpenStreetMap contributors — datos baixo **ODbL 1.0**.
> https://www.openstreetmap.org/copyright

## Atribución e uso

Este repositorio é público. Os datos proveñen de fontes administrativas
abertas e reutilizables; ao reutilizalos hai que **citar a fonte** indicada
en cada apartado (MITMA, Xunta de Galicia e OpenStreetMap / ODbL).

Para condicións legais detalladas, consulta o portal de datos abertos de cada
organismo. Non se inclúen aquí datos persoais nin información confidencial.

## Notas

- `tramos_mitma.csv` e `calibracion_pk.csv` **non** están incluídos: os ficheiros
  orixinais estaban baleiros (0 bytes). Hai que xeralos co script de preparación
  de datos a partir destes `.geojson`.
- Se nun futuro se engaden conxuntos grandes, valora usar Git LFS ou
  manteros fóra do repo e documentar a descarga.
