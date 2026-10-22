# Cycle Escape

**Encuentra por dónde escapar de la ciudad en bicicleta de carretera.**

> "Estoy en una ciudad que no conozco. ¿Por qué dirección debería salir para alcanzar
> carreteras tranquilas y con poco tráfico lo antes posible?"

Cycle Escape es una aplicación web para ciclistas de carretera que visitan una ciudad que
no conocen. En lugar de pedir un destino, el usuario indica dónde está y cómo le gusta
rodar. La aplicación analiza la red viaria de alrededor y propone varios **corredores de
escape** hacia carreteras tranquilas, explicando cuánto tarda en salir de la ciudad y qué
nivel de tráfico encontrará después.

El MVP y la demo del hackathon se centran en **Santiago de Compostela**, pero la
arquitectura no está atada a la ciudad: el origen, los datos de tráfico y la red viaria son
parámetros de entrada.

---

## Qué es y qué no es

| Es | No es |
|---|---|
| Un explorador de **salidas** de la ciudad | Un planificador de rutas A → B |
| Una herramienta para descubrir carreteras tranquilas | Un navegador GPS |
| Una estimación transparente de estrés viario | Una auditoría científica de seguridad |
| Una demo con datos oficiales de tráfico y OSM | Un producto con cuentas, historial o sincronización |

El usuario no necesita un destino concreto. La pregunta que responde la aplicación es
**"¿hacia dónde salgo?"**, no **"¿cómo llego a este punto?"**.

---

## Conceptos principales

### Escape Point

Primer punto de la ruta a partir del cual el ciclista alcanza una **red sostenida** de
carreteras predominantemente tranquilas y de bajo estrés.

No es:

- el límite administrativo de la ciudad;
- simplemente la primera carretera con poco tráfico;
- un punto arbitrario a mitad de ruta.

Los kilómetros posteriores al Escape Point también deben mantenerse razonablemente
tranquilos. Por eso el punto se valida contra una ventana de red, no contra un único
segmento.

### Escape Time

Tiempo necesario para llegar desde el origen del usuario hasta el Escape Point, a la
velocidad media configurada.

### Road Stress

Estimación interpretable de lo incómodo o estresante que puede resultar un tramo de
carretera para un ciclista de carretera. Escala **0–100**, donde **más alto = más estrés**.

Puede combinar:

- volumen de tráfico medido (IMD/AADT);
- porcentaje de vehículos pesados;
- tipo de carretera;
- velocidad;
- número de carriles;
- acceso o infraestructura ciclista;
- otros atributos de OpenStreetMap.

**No se llama "Safety Score"**: estimamos estrés viario y exposición al tráfico, no
demostramos científicamente la seguridad de una carretera.

### QuietScore

Puntuación orientada al usuario, derivada del Road Stress. Escala **0–100**, donde **más
alto = más tranquilo**. Se calcula sobre la red posterior al Escape Point, no solo sobre el
tramo urbano de salida.

---

## Cómo funciona

1. **Grafo base OSM.** Se descarga la red viaria con OSMnx y se construye un grafo de
   NetworkX. OpenStreetMap es siempre la fuente de la geometría y del routing.
2. **Enriquecimiento de tráfico.** Los segmentos OSM se cruzan geométricamente con los
   aforos de la Xunta de Galicia y de MITMA. Cada segmento puede quedar con IMD, porcentaje
   de pesados, fuente, año y confianza.
3. **Road Stress por segmento.** Si hay medición, se usa. Si no, se estima a partir de
   atributos OSM (tipo de vía, carriles, velocidad, superficie, etc.).
4. **Direcciones candidatas.** Se exploran varios corredores alrededor del origen (por
   ejemplo O, N, S, SE, E) y se calcula la mejor salida de cada uno.
5. **Detección del Escape Point.** Para cada corredor se busca el primer punto desde el que
   la red siguiente es sostenidamente tranquila.
6. **Métricas y ranking.** Escape Time, distancia hasta el Escape Point, QuietScore
   posterior, confianza de datos y avisos.
7. **API JSON → frontend.** El backend devuelve una ruta recomendada y alternativas con
   geometría GeoJSON lista para pintar.

### Regla de oro sobre los datos

**La ausencia de mediciones de tráfico NUNCA se interpreta como tráfico cero.** Las
carreteras sin aforo usan una estimación basada en OSM y se marcan como tales, con su
nivel de confianza. La interfaz debe poder distinguir "medido" de "estimado".

---

## Fuentes de datos

| Fuente | Qué aporta | Uso actual | Año / cobertura |
|---|---|---|---|
| OpenStreetMap + OSMnx | Red viaria, geometría, tipo, superficie, carriles, velocidad, restricciones | Grafo base de routing y estimación de estrés | Actual |
| Xunta de Galicia | Observaciones oficiales de tráfico, segmentos GeoJSON, IMD, % pesados | Enriquecimiento de carreteras gallegas | Principalmente 2025 |
| MITMA | Aforos de carreteras nacionales, IMD, ligeros, pesados, geometría | Enriquecimiento de N-550 y N-525 en el entorno de Santiago | Principalmente 2022 |

Los datos crudos y procesados **no se versionan** en el repositorio (ver `.gitignore`).
Cada desarrollador los obtiene localmente. La documentación detallada de normalización y
matching corresponde al área de datos.

Atribución obligatoria en la interfaz: **© OpenStreetMap contributors** y mención a la
Xunta de Galicia y MITMA como fuentes de los aforos.

---

## Experiencia de usuario

### Entradas

- Posición de origen: clic en el mapa, geolocalización o coordenadas.
- Perfil de bicicleta de carretera / preferencia por asfalto.
- Velocidad media (por defecto, 22 km/h).
- Aversión al tráfico (baja / media / alta).
- Preferencia entre salida directa y salida tranquila.

### Salidas

Varios corredores candidatos, por ejemplo:

- Oeste vía Roxos
- Norte hacia Sigüeiro
- Sur hacia O Milladoiro
- Sureste hacia Cacheiras
- Este hacia Aríns

Para cada uno:

- Escape Time;
- distancia hasta el Escape Point;
- QuietScore después del Escape Point;
- confianza de los datos;
- fuente y año de los aforos;
- avisos cuando un tramo va estimado.

La ruta recomendada se resalta sobre el mapa y el **Escape Point se muestra de forma muy
destacada**. El resto de alternativas queda visible pero atenuado.

### Colores de Road Stress

| Color | Estrés | Banda orientativa |
|---|---|---|
| Rojo | Alto | 76–100 |
| Naranja | Medio-alto | 51–75 |
| Amarillo | Transición | 26–50 |
| Verde | Tranquilo | 0–25 |

Los umbrales son una convención de interfaz y pueden ajustarse junto con el equipo de
routing. El significado (rojo = peor) no debe invertirse.

---

## Stack previsto

| Capa | Tecnología |
|---|---|
| Frontend | React + Vite + TypeScript + Leaflet / React-Leaflet |
| Backend | FastAPI + OSMnx + NetworkX + GeoPandas |
| Datos | GeoJSON normalizado + grafo OSM en caché local |
| Contrato | JSON sobre HTTP, geometrías GeoJSON |

Se prioriza la simplicidad: sin autenticación, sin base de datos, sin cuentas de usuario y
sin frameworks de estado pesados. Es un hackathon de un día.

---

## Estructura del repositorio

```text
cycle-escape/
├── frontend/          # Interfaz React + mapa (Javi)
├── backend/app/       # FastAPI, OSM/routing, scoring (Xián)
├── data/
│   ├── raw/           # GeoJSON originales de Xunta y MITMA (no versionado)
│   └── processed/     # Datos normalizados y enriquecidos (no versionado)
├── tests/             # Pruebas del backend
├── docs/              # Contrato de API, guion de demo y documentación compartida
├── AGENTS.md          # Reglas de colaboración para personas y agentes
└── README.md
```

---

## API

El contrato detallado está en [`docs/api-contract.md`](docs/api-contract.md).

Resumen: el frontend enviará el origen y las preferencias, y recibirá una ruta recomendada
más alternativas, con geometría GeoJSON, Escape Point, métricas y metadatos de tráfico.

Estos nombres de campo son **compartidos y están congelados** hasta que el equipo acuerde
un cambio:

`imd`, `heavy_pct`, `traffic_source`, `traffic_year`, `traffic_confidence`,
`road_stress`, `quiet_score`, `escape_point`, `escape_time_min`,
`distance_to_escape_km`.

El frontend funciona desde el primer día con un mock que respeta esta forma, de modo que no
depende de que el backend esté terminado.

---

## Puesta en marcha

### Requisitos

- Node.js 20 o superior (probado con Node 22) y npm.
- Python 3.11 o superior.
- Conexión a internet para las teselas del mapa.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

> El scaffold del frontend se añadirá en la primera tarea de interfaz. Hasta entonces esta
> sección describe los comandos previstos.

### Backend

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

> El backend está en construcción. `requirements.txt` y los módulos de `backend/app/` se
> completarán durante el hackathon.

### Datos

Los GeoJSON de Xunta y MITMA no están en el repositorio. Se solicitan al responsable de
datos o se descargan de las fuentes oficiales y se colocan en `data/raw/xunta/` y
`data/raw/mitma/`.

---

## Equipo y responsabilidades

| Persona | Área | Ámbito |
|---|---|---|
| Javi | Frontend | `frontend/`: React, mapa, controles, visualización, métricas |
| Eva | Datos de tráfico | GeoJSON de Xunta y MITMA, normalización, metadatos, matching |
| Xián | OSM / routing | Grafo, Road Stress, rutas candidatas, Escape Point, API |

Las reglas de colaboración y los límites de cada área están en [`AGENTS.md`](AGENTS.md).

---

## Alcance del MVP

Incluido:

- selección de origen en Santiago de Compostela;
- preferencias básicas de velocidad, aversión y superficie;
- entre 3 y 5 corredores candidatos;
- ruta recomendada + alternativas;
- Escape Point y métricas;
- coloreado por Road Stress;
- fuente, año y confianza de los datos;
- fallback a datos mock para la demo.

Fuera de alcance:

- autenticación, cuentas, historial o bases de datos;
- navegación giro a giro;
- planificación A → B;
- aplicación móvil nativa;
- cobertura nacional o multi-ciudad en producción;
- garantías de seguridad viaria.

---

## Estado actual

| Elemento | Estado |
|---|---|
| Estructura del repositorio | Listo |
| Documentación compartida | Redactada; pendiente de revisión del equipo |
| Contrato de API | Propuesta, pendiente de validación |
| Backend | Pendiente |
| Frontend | Pendiente |
| Mock de respuesta | Pendiente |
| Demo | Pendiente |

### Próximos pasos

1. Validar el contrato de API entre los tres desarrolladores.
2. Crear el scaffold del frontend y el mock de Santiago.
3. Implementar el pipeline de datos y el grafo OSM.
4. Integrar frontend y backend.
5. Ensayar la demo con [`docs/demo-script.md`](docs/demo-script.md).

---

## Documentación

- [`AGENTS.md`](AGENTS.md): reglas de colaboración, propiedad del código y convenciones.
- [`docs/api-contract.md`](docs/api-contract.md): propuesta de contrato HTTP/JSON.
- [`docs/demo-script.md`](docs/demo-script.md): guion y plan B para la presentación.

---

## Limitaciones que conviene explicar

- El Road Stress es una **estimación** basada en datos disponibles, no una medida de
  seguridad.
- La cobertura de aforos es parcial; los tramos sin datos se estiman con OSM y se marcan
  con menor confianza.
- Los datos de MITMA usados son principalmente de 2022 y los de la Xunta de 2025; la
  antigüedad se muestra siempre que sea posible.
- La demo se limita a Santiago de Compostela, aunque el diseño no dependa de esa ciudad.
