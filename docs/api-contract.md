# Contrato de API — v0.1

> **Estado:** implementado en `backend/app/models.py` y cubierto por los tests de
> `tests/test_api.py` y `tests/test_contract_models.py`. Los cambios deben ser aditivos y,
> a ser posible, opcionales para no romper a los consumidores.
>
> **Objetivo:** fijar una respuesta única que permita al frontend pintar la ruta
> recomendada, las alternativas, el Escape Point, el coloreado por estrés y los metadatos
> de tráfico. El frontend consume la API real; no hay datos mock.
>
> **Regla:** los campos compartidos no se renombran sin coordinación. Los cambios deben ser
> aditivos y, a ser posible, opcionales.

---

## 1. Convenciones

| Aspecto | Convención |
|---|---|
| Formato | JSON sobre HTTP |
| Nombres | `snake_case` |
| Geometrías | GeoJSON (`LineString`), coordenadas `[lon, lat]` |
| Distancias | kilómetros (`*_km`) |
| Tiempos | minutos (`*_min`) |
| Estrés | `road_stress` 0–100, alto = peor |
| Tranquilidad | `quiet_score` 0–100, alto = mejor |
| Fechas | ISO 8601 UTC |
| Nulos | `null` cuando no hay dato; **nunca 0 como sustituto** |
| Versión | `schema_version` en la respuesta |

---

## 2. Endpoints

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/api/health` | Comprobación de vida y estado de datos |
| `POST` | `/api/escape-routes` | Buscar corredores de escape para un origen |

### `GET /api/health`

```json
{
  "status": "ok",
  "osm_graph_loaded": true,
  "traffic_layers": ["xunta", "mitma", "osm_estimate"],
  "schema_version": "0.1"
}
```

Si el grafo no está cargado, `status` puede ser `"degraded"` y `osm_graph_loaded: false`.
El frontend usa este endpoint solo para diagnóstico; nunca debe bloquear la demo si falla.

### `POST /api/escape-routes`

#### Petición

```json
{
  "origin": { "lat": 42.8782, "lon": -8.5448 },
  "avg_speed_kmh": 22,
  "traffic_aversion": 0.6,
  "traffic_lambda": 0.5,
  "surface_preference": "asphalt",
  "route_preference": "balanced",
  "max_candidates": 5
}
```

| Campo | Tipo | Obligatorio | Rango / valores | Descripción |
|---|---|---|---|---|
| `origin.lat` | number | Sí | -90..90 | Latitud del origen |
| `origin.lon` | number | Sí | -180..180 | Longitud del origen |
| `avg_speed_kmh` | number | No | 10..40 | Velocidad media; por defecto 22 |
| `traffic_aversion` | number | No | 0..1 | 0 = tolera tráfico, 1 = lo evita a toda costa; por defecto 0.5 |
| `traffic_lambda` | number | No | 0..1 | Peso continuo del componente de tráfico; 0 = directo, 1 = tranquilo. Si se omite, se usan los pesos de `route_preference` |
| `surface_preference` | string | No | `asphalt` \| `mixed` \| `any` | Preferencia de superficie; por defecto `asphalt`. En v0.1 se acepta, pero no filtra el grafo: el Road Stress ya penaliza superficies no asfaltadas |
| `route_preference` | string | No | `direct` \| `balanced` \| `quiet` | Equilibrio entre rapidez y tranquilidad; por defecto `balanced` |
| `max_candidates` | integer | No | 1..7 | Número máximo de corredores; por defecto 5 |

Notas:

- El backend no geocodifica: el origen llega como coordenadas. La búsqueda y la
  geocodificación inversa las hace el frontend con Nominatim.
- `traffic_aversion` modula el coste del routing: una aversión alta acepta rodeos para
  evitar ejes estresantes. Se puede presentar en la UI como Baja/Media/Alta, pero viaja
  como 0–1.
- `traffic_lambda` pondera el ranking final (tiempo hasta el Escape Point frente a
  QuietScore posterior). El frontend mantiene además `route_preference` derivado de λ
  (`direct` < 0.34, `balanced`, `quiet` > 0.66) para que un backend que aún no lea λ siga
  funcionando.
- `max_candidates` limita el número de corredores devueltos; el backend puede devolver
  menos si hay direcciones sin ruta alcanzable.

---

## 3. Respuesta

### Estructura de alto nivel

```json
{
  "schema_version": "0.1",
  "request_id": "req_20261022_101500",
  "generated_at": "2026-10-22T10:15:00Z",
  "origin": { "lat": 42.8782, "lon": -8.5448 },
  "recommended_route_id": "oeste-roxos",
  "routes": [],
  "warnings": []
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `schema_version` | string | Versión del contrato |
| `request_id` | string | Identificador de la petición para depurar |
| `generated_at` | string | Momento de generación |
| `origin` | object | Origen efectivamente usado |
| `recommended_route_id` | string | `id` de la ruta recomendada |
| `routes` | array | Rutas ordenadas por recomendación |
| `warnings` | array de string | Avisos globales (datos incompletos, etc.) |

### Ruta

```json
{
  "id": "oeste-roxos",
  "label": "Oeste vía Roxos",
  "direction": "W",
  "is_recommended": true,
  "escape_time_min": 18,
  "distance_to_escape_km": 6.4,
  "quiet_score": 84,
  "avg_road_stress": 42,
  "escape_point": {
    "lat": 42.872,
    "lon": -8.59,
    "name": "Roxos"
  },
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [-8.5448, 42.8782],
      [-8.552, 42.876],
      [-8.564, 42.874],
      [-8.578, 42.873],
      [-8.59, 42.872]
    ]
  },
  "segments": [],
  "traffic_summary": {},
  "warnings": []
}
```

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Identificador estable y único |
| `label` | string | Sí | Texto para mostrar, p. ej. "Oeste vía Roxos" |
| `direction` | string | Sí | `N`, `NE`, `E`, `SE`, `S`, `SW`, `W`, `NW` |
| `is_recommended` | boolean | Sí | Coherente con `recommended_route_id` |
| `escape_time_min` | number | Sí | Tiempo hasta el Escape Point |
| `distance_to_escape_km` | number | Sí | Distancia hasta el Escape Point |
| `quiet_score` | number | Sí | QuietScore de la red posterior al Escape Point (0–100) |
| `avg_road_stress` | number | No | Estrés medio de toda la ruta (0–100) |
| `escape_point` | object | Sí | Coordenadas del Escape Point; `name` puede ser `null` |
| `geometry` | GeoJSON LineString | Sí | Trazado completo de la ruta |
| `segments` | array | Recomendado | Segmentos para colorear por estrés |
| `traffic_summary` | object | Sí | Resumen de cobertura y confianza |
| `warnings` | array de string | No | Avisos específicos de la ruta |

Notas:

- `geometry` es la fuente autoritativa para dibujar la línea completa.
- `segments` permite el coloreado por tramos. Si no llega, el frontend pinta la ruta con un
  color único derivado de `avg_road_stress` y lo indica en la interfaz. En v0.1 el backend
  los envía para todas las rutas.
- `escape_point` debe caer sobre la geometría de la ruta. `escape_point.name` es opcional:
  si es `null`, el frontend debe mostrar una etiqueta genérica y nunca asumir que existe.
- `distance_to_escape_km` es la distancia recorrida desde el origen hasta el Escape Point,
  no la distancia en línea recta.
- `quiet_score` se calcula sobre la red posterior al Escape Point, no sobre el tramo
  urbano de salida.
- Si el origen ya está en una zona sostenidamente tranquila, el Escape Point puede quedar
  a 0 km y `escape_time_min` a 0. Es un resultado válido; la UI debería explicarlo como
  "ya estás en zona tranquila" en lugar de mostrar un cero sin contexto. En v0.1 el
  frontend descarta los corredores con Escape Point a menos de 1,5 km del origen y muestra
  un aviso si no queda ninguno.

### Segmento

```json
{
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [-8.5448, 42.8782],
      [-8.552, 42.876]
    ]
  },
  "road_name": "Rúa de San Pedro",
  "highway": "residential",
  "surface": "asphalt",
  "road_stress": 74,
  "imd": 9200,
  "heavy_pct": 5.1,
  "traffic_source": "xunta",
  "traffic_year": 2025,
  "traffic_confidence": "high"
}
```

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `geometry` | GeoJSON LineString | No | Tramo |
| `road_name` | string | Sí | Nombre de la vía si se conoce |
| `highway` | string | Sí | Valor OSM (`residential`, `secondary`, `track`…) |
| `surface` | string | Sí | Superficie OSM |
| `road_stress` | number | No | 0–100, alto = peor |
| `imd` | number | Sí | Intensidad media diaria; `null` si no hay aforo |
| `heavy_pct` | number | Sí | Porcentaje de pesados (0–100); `null` si no hay dato |
| `traffic_source` | string | No | `xunta` \| `mitma` \| `osm_estimate` |
| `traffic_year` | integer | Sí | Año del aforo; `null` si es estimación |
| `traffic_confidence` | string | No | `high` \| `medium` \| `low` |

Reglas de datos:

- Si `traffic_source` es `osm_estimate`, entonces `imd` y `traffic_year` deben ser `null`.
- Si `traffic_source` es `xunta` o `mitma`, `imd` debería estar presente. Si falta, el
  backend fuerza `traffic_confidence: "low"`; la capa normalizada no debería producir ese
  caso.
- `heavy_pct` se expresa en porcentaje (0–100), no en fracción.

### Resumen de tráfico de la ruta

```json
{
  "sources": ["xunta", "osm_estimate"],
  "years": [2025],
  "measured_share": 0.66,
  "confidence": "medium"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `sources` | array de string | Fuentes presentes en la ruta |
| `years` | array de integer | Años de los aforos usados |
| `measured_share` | number | Fracción 0–1 de la distancia con aforo medido |
| `confidence` | string | Confianza agregada `high` \| `medium` \| `low` |

### Semántica implementada de `traffic_confidence`

| Valor | Criterio |
|---|---|
| `high` | Xunta con año real ≤ 3 años respecto al actual |
| `medium` | Xunta más antiguo o sin año; MITMA (aforo de 2022 en el MVP) |
| `low` | Sin aforo; Road Stress estimado solo con atributos OSM |

Confianza agregada de la ruta (`traffic_summary.confidence`) tal como la devuelve el
backend:

| Valor | Criterio |
|---|---|
| `high` | `measured_share >= 0.75` y todos los tramos medidos son `high` |
| `medium` | Hay algún tramo medido, pero no se cumple `high` |
| `low` | `measured_share == 0`: toda la ruta es `osm_estimate` |

> **Nota de implementación (pendiente de unificar):** el frontend aplica además una
> política de presentación en `frontend/src/utils.ts` distinta de la del backend:
> 0 % medido → `low`, hasta 2 % → `medium`, más de 2 % → `high`. Es una decisión de
> producto adoptada en la PR #9 y todavía no está alineada con la respuesta del backend;
> hasta unificarla, el contrato describe la política del backend y la UI puede mostrar un
> nivel superior. La UI solo muestra los tres niveles y su explicación; no debe inferir
> precisión que los datos no tienen.

---

## 4. Ejemplo completo

> Geometrías y valores **simplificados y ficticios**, solo como ejemplo del contrato. No
> son mediciones reales.

```json
{
  "schema_version": "0.1",
  "request_id": "req_demo_001",
  "generated_at": "2026-10-22T10:15:00Z",
  "origin": { "lat": 42.8782, "lon": -8.5448 },
  "recommended_route_id": "oeste-roxos",
  "routes": [
    {
      "id": "oeste-roxos",
      "label": "Oeste vía Roxos",
      "direction": "W",
      "is_recommended": true,
      "escape_time_min": 18,
      "distance_to_escape_km": 6.4,
      "quiet_score": 84,
      "avg_road_stress": 42,
      "escape_point": { "lat": 42.872, "lon": -8.59, "name": "Roxos" },
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [-8.5448, 42.8782],
          [-8.552, 42.876],
          [-8.564, 42.874],
          [-8.578, 42.873],
          [-8.59, 42.872]
        ]
      },
      "segments": [
        {
          "geometry": {
            "type": "LineString",
            "coordinates": [[-8.5448, 42.8782], [-8.552, 42.876]]
          },
          "road_name": "Rúa de San Pedro",
          "highway": "residential",
          "surface": "asphalt",
          "road_stress": 74,
          "imd": 9200,
          "heavy_pct": 5.1,
          "traffic_source": "xunta",
          "traffic_year": 2025,
          "traffic_confidence": "high"
        },
        {
          "geometry": {
            "type": "LineString",
            "coordinates": [[-8.552, 42.876], [-8.564, 42.874]]
          },
          "road_name": "AC-543",
          "highway": "secondary",
          "surface": "asphalt",
          "road_stress": 48,
          "imd": null,
          "heavy_pct": null,
          "traffic_source": "osm_estimate",
          "traffic_year": null,
          "traffic_confidence": "low"
        },
        {
          "geometry": {
            "type": "LineString",
            "coordinates": [[-8.564, 42.874], [-8.59, 42.872]]
          },
          "road_name": "Camiño de Roxos",
          "highway": "tertiary",
          "surface": "asphalt",
          "road_stress": 18,
          "imd": 650,
          "heavy_pct": 1.2,
          "traffic_source": "xunta",
          "traffic_year": 2025,
          "traffic_confidence": "high"
        }
      ],
      "traffic_summary": {
        "sources": ["xunta", "osm_estimate"],
        "years": [2025],
        "measured_share": 0.66,
        "confidence": "medium"
      },
      "warnings": ["Un tramo sin aforo usa estimación OSM"]
    },
    {
      "id": "norte-sigueiro",
      "label": "Norte hacia Sigüeiro",
      "direction": "N",
      "is_recommended": false,
      "escape_time_min": 24,
      "distance_to_escape_km": 8.1,
      "quiet_score": 71,
      "avg_road_stress": 51,
      "escape_point": { "lat": 42.92, "lon": -8.525, "name": "Salida norte" },
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [-8.5448, 42.8782],
          [-8.54, 42.888],
          [-8.532, 42.9],
          [-8.525, 42.92]
        ]
      },
      "segments": [
        {
          "geometry": {
            "type": "LineString",
            "coordinates": [[-8.5448, 42.8782], [-8.54, 42.888]]
          },
          "road_name": "Rúa da Pastoriza",
          "highway": "residential",
          "surface": "asphalt",
          "road_stress": 66,
          "imd": 7100,
          "heavy_pct": 3.4,
          "traffic_source": "xunta",
          "traffic_year": 2025,
          "traffic_confidence": "high"
        },
        {
          "geometry": {
            "type": "LineString",
            "coordinates": [[-8.54, 42.888], [-8.525, 42.92]]
          },
          "road_name": "CP-0201",
          "highway": "tertiary",
          "surface": "asphalt",
          "road_stress": 36,
          "imd": null,
          "heavy_pct": null,
          "traffic_source": "osm_estimate",
          "traffic_year": null,
          "traffic_confidence": "low"
        }
      ],
      "traffic_summary": {
        "sources": ["xunta", "osm_estimate"],
        "years": [2025],
        "measured_share": 0.45,
        "confidence": "medium"
      },
      "warnings": []
    },
    {
      "id": "sur-milladoiro",
      "label": "Sur hacia O Milladoiro",
      "direction": "S",
      "is_recommended": false,
      "escape_time_min": 31,
      "distance_to_escape_km": 10.2,
      "quiet_score": 63,
      "avg_road_stress": 58,
      "escape_point": { "lat": 42.845, "lon": -8.57, "name": "O Milladoiro" },
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [-8.5448, 42.8782],
          [-8.55, 42.865],
          [-8.56, 42.855],
          [-8.57, 42.845]
        ]
      },
      "segments": [
        {
          "geometry": {
            "type": "LineString",
            "coordinates": [[-8.5448, 42.8782], [-8.56, 42.855]]
          },
          "road_name": "N-550",
          "highway": "trunk",
          "surface": "asphalt",
          "road_stress": 88,
          "imd": 23000,
          "heavy_pct": 9.8,
          "traffic_source": "mitma",
          "traffic_year": 2022,
          "traffic_confidence": "medium"
        },
        {
          "geometry": {
            "type": "LineString",
            "coordinates": [[-8.56, 42.855], [-8.57, 42.845]]
          },
          "road_name": "Rúa do Agro",
          "highway": "tertiary",
          "surface": "asphalt",
          "road_stress": 34,
          "imd": null,
          "heavy_pct": null,
          "traffic_source": "osm_estimate",
          "traffic_year": null,
          "traffic_confidence": "low"
        }
      ],
      "traffic_summary": {
        "sources": ["mitma", "osm_estimate"],
        "years": [2022],
        "measured_share": 0.55,
        "confidence": "medium"
      },
      "warnings": ["Aforo de MITMA de 2022"]
    }
  ],
  "warnings": ["Los datos de tráfico son parciales: hay tramos estimados con OSM"]
}
```

---

## 5. Mapeo a la interfaz

| Elemento de UI | Campo |
|---|---|
| Línea de la ruta | `routes[].geometry` |
| Color por tramo | `routes[].segments[].road_stress` |
| Marcador destacado | `routes[].escape_point` |
| Tiempo hasta salir | `routes[].escape_time_min` |
| Distancia hasta salir | `routes[].distance_to_escape_km` |
| Tranquilidad posterior | `routes[].quiet_score` |
| Etiqueta del corredor | `routes[].label` / `direction` |
| Ruta recomendada | `recommended_route_id` / `is_recommended` |
| Fuente y año | `traffic_summary` y `segments[].traffic_source` / `traffic_year` |
| Confianza | `traffic_summary.confidence` / `segments[].traffic_confidence` |
| Avisos | `warnings` |

### Colores propuestos

| `road_stress` | Color | Etiqueta |
|---|---|---|
| 0–25 | Verde | Tranquilo |
| 26–50 | Amarillo | Transición |
| 51–75 | Naranja | Estrés medio-alto |
| 76–100 | Rojo | Estrés alto |

---

## 6. Errores

Formato estable:

```json
{
  "error": {
    "code": "NO_ROUTES_FOUND",
    "message": "No se han encontrado corredores de escape para este origen.",
    "details": {}
  }
}
```

| Código HTTP | `code` | Cuándo |
|---|---|---|
| 400 | `INVALID_ORIGIN` | Coordenadas fuera de rango o sin red cercana |
| 400 | `INVALID_PARAMETER` | Velocidad, aversión o preferencia inválida |
| 404 | `OUTSIDE_COVERAGE` | Origen fuera de la zona con datos cargados |
| 500 | `ROUTING_ERROR` | Fallo interno del grafo o del cálculo |
| 503 | `DATA_NOT_READY` | Grafo o capas de tráfico sin cargar |

El frontend debe mostrar un mensaje comprensible y ofrecer reintentar. No usa datos mock
ni inventa resultados.

---

## 7. Requisitos para el frontend

- Tratar `geometry` y `segments[].geometry` como GeoJSON `[lon, lat]`.
- No asumir que `segments` existe: degradar a color único.
- No asumir que `imd`, `heavy_pct`, `traffic_year` o `escape_point.name` existen.
- Si `escape_point.name` es `null`, usar una etiqueta genérica; nunca pasar `null` a una
  función que espere texto.
- Mostrar "Sin aforo (estimado)" cuando `traffic_source` sea `osm_estimate`.
- Ordenar por el orden de `routes`, que ya viene priorizado por el backend.
- No recalcular el ranking en el cliente; solo mostrar.

---

## 8. Decisiones cerradas y pendientes

### Cerradas para v0.1

1. La ruta definitiva es `POST /api/escape-routes`; `GET /api/health` solo diagnostica.
2. `quiet_score` se expone por ruta, calculado sobre la red posterior al Escape Point.
3. Los umbrales de `traffic_confidence` son los de la sección 3.
4. Se devuelven hasta 7 candidatos; 5 por defecto y configurable con `max_candidates`.
5. El backend compone `label`; el frontend no recalcula el ranking.
6. No hay endpoint de configuración de ciudad en v0.1: la demo está centrada en Santiago.
7. Si el origen está fuera del grafo o a más de 1 km de la red, se devuelve
   `OUTSIDE_COVERAGE`. Si está en el agua pero dentro de la cobertura, se usa el nodo más
   cercano; si no hay rutas alcanzables, `NO_ROUTES_FOUND`.

### Pendientes

- Aplicar `surface_preference` en el coste de routing.
- Desacoplar la ciudad de demo y soportar varias cachés de grafo.
- Decidir si `quiet_score` se expone también por segmento.
- Ampliar la cobertura de aforos y revisar los umbrales con ciclistas locales.

Cualquier respuesta debe reflejarse aquí y en el código en el mismo PR.
