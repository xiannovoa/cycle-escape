# Datos en crudo (`data/raw`)

Conxuntos de datos de entrada do proxecto. Son ficheiros pequenos (~2,8 MB en total),
por iso se versionan no repositorio: calquera persoa do equipo que clone o repo
ten todo o necesario para traballar sen pasos previos.

> Os artefactos derivados van en `data/processed/` e **non** se versionan
> (ver `.gitignore`). Pódense rexenerar a partir destes ficheiros.

## Estrutura

```
data/raw/
├── mitma/
│   ├── mitma_santiago.geojson     IMD de todos os tramos (área de Santiago)
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
