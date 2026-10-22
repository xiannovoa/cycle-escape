# Metadatos del repositorio en GitHub

Textos preparados para rellenar el bloque **About** de
[`xiannovoa/cycle-escape`](https://github.com/xiannovoa/cycle-escape). El bloque About no
vive en el repositorio: hay que aplicarlo desde la interfaz de GitHub, con `gh` o con la API
REST.

---

## Descripción (About)

> Web app para ciclistas de carretera que llegan a una ciudad sin destino: analiza la red
> OSM, cruza aforos de la Xunta y MITMA y propone corredores de escape hacia carreteras
> tranquilas. Muestra Escape Point, Escape Time, QuietScore y confianza del dato. Proyecto
> del Hackathon de la ETSE 2026.

Versión de una línea, para sitios donde no quepa el párrafo:

> Encuentra por dónde escapar de la ciudad en bicicleta de carretera.

## Website

Dejar vacío hasta que exista una demo pública desplegada. No conviene apuntar a
`localhost`.

## Topics

GitHub admite hasta 20 topics. Propuesta:

```text
cycling
road-cycling
openstreetmap
osmnx
fastapi
react
typescript
leaflet
geospatial
routing
traffic-data
santiago-de-compostela
galicia
hackathon
etse-2026
mobility
sustainable-mobility
data-visualization
python
quiet-roads
```

---

## Cómo aplicarlo

### Opción A: interfaz web

1. Abrir <https://github.com/xiannovoa/cycle-escape>.
2. Pulsar el engranaje **⚙** del bloque **About**.
3. Pegar la descripción.
4. Añadir los topics uno a uno.
5. Guardar con **Save changes**.

### Opción B: GitHub CLI

```bash
gh repo edit xiannovoa/cycle-escape \
  --description "Web app para ciclistas de carretera que llegan a una ciudad sin destino: analiza la red OSM, cruza aforos de la Xunta y MITMA y propone corredores de escape hacia carreteras tranquilas. Muestra Escape Point, Escape Time, QuietScore y confianza del dato. Proyecto del Hackathon de la ETSE 2026." \
  --add-topic cycling \
  --add-topic road-cycling \
  --add-topic openstreetmap \
  --add-topic osmnx \
  --add-topic fastapi \
  --add-topic react \
  --add-topic typescript \
  --add-topic leaflet \
  --add-topic geospatial \
  --add-topic routing \
  --add-topic traffic-data \
  --add-topic santiago-de-compostela \
  --add-topic galicia \
  --add-topic hackathon \
  --add-topic etse-2026 \
  --add-topic mobility \
  --add-topic sustainable-mobility \
  --add-topic data-visualization \
  --add-topic python \
  --add-topic quiet-roads
```

### Opción C: API REST desde PowerShell

Requiere un token con permiso de administración del repositorio. **No lo guardes en el
repositorio**; usable solo como variable de entorno local:

```powershell
$body = @{
  description = "Web app para ciclistas de carretera que llegan a una ciudad sin destino: analiza la red OSM, cruza aforos de la Xunta y MITMA y propone corredores de escape hacia carreteras tranquilas. Muestra Escape Point, Escape Time, QuietScore y confianza del dato. Proyecto del Hackathon de la ETSE 2026."
  topics = @(
    "cycling", "road-cycling", "openstreetmap", "osmnx", "fastapi",
    "react", "typescript", "leaflet", "geospatial", "routing",
    "traffic-data", "santiago-de-compostela", "galicia", "hackathon",
    "etse-2026", "mobility", "sustainable-mobility", "data-visualization",
    "python", "quiet-roads"
  )
} | ConvertTo-Json

Invoke-RestMethod -Method Patch `
  -Uri "https://api.github.com/repos/xiannovoa/cycle-escape" `
  -Headers @{
    Authorization = "Bearer $env:GITHUB_TOKEN"
    Accept = "application/vnd.github+json"
  } `
  -Body $body
```

---

## Notas

- La descripción debe mantenerse por debajo de los 350 caracteres de GitHub.
- Los topics no llevan espacios ni mayúsculas: GitHub los normaliza a minúsculas y guiones.
- Si se publica una demo, añadir la URL en **Website** y actualizar este documento en el
  mismo PR.
