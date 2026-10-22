Eres un asistente que me ayuda en un hackatón de IA (22-10-2026). Te doy el contexto completo de los datos que ya he preparado, para que continúes a partir de aquí sin repetir trabajo.

## El proyecto: FÓRA

FÓRA es una web para ciclistas de carretera que visitan Santiago de Compostela. Desde un punto de salida en Santiago, compara los corredores de salida de la ciudad y calcula para cada uno:
- **Escape Point**: el punto donde el ciclista sale por fin a carreteras tranquilas (poco tráfico).
- **Escape Time**: cuánto tarda en llegar a ese punto.

Corredores de salida: Roxos (O), Sigüeiro (N), Milladoiro (S), Cacheiras/A Estrada (SE), Aríns (E), Lavacolla (NE).

La red de calles sale de OpenStreetMap (OSMnx). El tráfico de cada carretera sale de los datos oficiales de intensidad media diaria (IMD) de la Xunta y del Ministerio de Transportes (MITMA).

## Archivo final de tráfico: `imd_santiago.geojson`

Es una única capa GeoJSON (EPSG:4326) con **39 tramos de carretera** (LineString). Ningún campo viene vacío.

Campos de cada tramo:
| Campo | Significado |
|---|---|
| Estrada | Carretera (AC-250, N-550...) |
| Corredor | Nombre del tramo o corredor (p. ej. "Sigüeiro (N-550) - Lavacolla (A-54)", "Milladoiro S") |
| PK_inicio, PK_fin | Punto kilométrico de inicio y fin del tramo |
| IMD | Intensidad media diaria (vehículos/día) |
| Pct_pesados | % de vehículos pesados |
| Anio | Año del dato (2025 Xunta, 2022 MITMA) |
| Fuente | "Xunta IMD 2025" o "MITMA 2022" |
| Nivel | Nivel de tráfico para ciclistas: tranquila (< 2000), moderada (2000–4999), alta (5000–9999), muy_alta (≥ 10000) |

Reparto: 6 tramos tranquilos, 13 moderados, 3 altos y 17 muy altos.

### Qué contiene
**Xunta (IMD 2025), 22 tramos**: carreteras autonómicas AC-250, AC-261, AC-453, AC-543, AC-841 y AC-960. Descargadas de la capa ArcGIS de la Xunta (`ideg.xunta.gal/.../Mapa_Trafico_OGC/MapServer/9`). Campos originales: IMD_2025, P_porcenta (% pesados), Pq_inicio/Pq_fin (PK), Treito (nombre del tramo).

**MITMA (mapa de tráfico 2022), 17 tramos** de carreteras nacionales, copiados a mano del visor mapatrafico.transportes.gob.es:
- N-550 norte, hacia Sigüeiro: PK 49–57.84, 3 tramos, IMD 16.035–20.396.
- N-550 sur, de Milladoiro hacia Padrón: PK 67.075–77.4, 5 tramos, IMD 15.314–25.074.
- N-525 hacia el sureste (A Susana): PK 326.9–337.74, 5 tramos, IMD 5.629–14.178.
- N-634 hacia el noreste (O Empalme / Teixeiro): PK 688.8–709.11, 4 tramos, IMD ~4.390 y 26 % de pesados.

Como el MITMA no da geometría descargable, la geometría de sus tramos se generó así: se baja la carretera de OSM (Overpass, ref=N-xxx) y se corta entre el PK de inicio y el de fin. Para traducir PK a metros se usaron 2 puntos de calibración por corredor (PK conocido + coordenadas).

### Limitaciones conocidas
- La **N-550 sur** sale unos 20 % más estirada de lo real (uno de los puntos de calibración está algo desplazado). Los tramos van por la carretera correcta.
- Hay un **hueco sin dato en la N-550 sur, PK 68.62–69** (unos 460 m). Recomendación: darle la IMD más alta de sus vecinos (25.074), para no hacerlo parecer más tranquilo de lo que es.
- Los datos MITMA son de **2022** y los de la Xunta de **2025**.
- La **N-634 no es la carretera de Lavacolla**: va hacia O Empalme y Teixeiro. La que pasa por Lavacolla y el aeropuerto parece la N-547, que no está en los datos. El corredor de Lavacolla se cubre en parte con la AC-250 (Sigüeiro–Lavacolla).
- Las carreteras sin dato de IMD (calles urbanas, pistas, carreteras municipales) no están en la capa. Hay que decidir cómo tratarlas en el cálculo (p. ej. asumir tráfico bajo si son vías locales, o usar el tipo de vía de OSM).

## Scripts (Python, ya funcionan en mi ordenador con Windows/Anaconda)
- `descargar_xunta.py`: descarga los 6 AC de la Xunta (`AC-xxx.geojson`).
- `tramos_a_geojson.py` + `tramos_mitma.csv` + `calibracion_pk.csv`: generan `mitma_santiago.geojson` (necesita shapely y pyproj).
- `unir_imd.py`: une Xunta y MITMA en `imd_santiago.geojson`, con campos comunes y el Nivel.

## Lo siguiente
Usar `imd_santiago.geojson` en FÓRA: cruzar sus tramos con las aristas del grafo de OSMnx (por ejemplo, asignando a cada arista la IMD del tramo más cercano a menos de unos 30 m y con la misma ref), y calcular para cada corredor el Escape Point (el primer punto de la ruta a partir del cual el ciclista circula por vías de nivel "tranquila") y el Escape Time.
