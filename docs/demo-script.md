# Guion de demo — Cycle Escape

> Documento de trabajo para el equipo. Objetivo: una demo de **3 minutos** que explique el
> problema, muestre el producto y deje claro qué es una estimación y qué está medido.
> Proyecto desarrollado para el **Hackathon de la ETSE 2026**.
>
> **Estado:** guion actualizado a la v0.1. Las cifras de ejemplo corresponden a la caché v2
> de Santiago, origen en el centro, 22 km/h, aversión alta (0,85) y prioridad 0,65. Si al
> ensayar cambian, **narrar lo que aparezca en pantalla**, no las cifras de este documento.

---

## 1. Mensaje central

> "No necesitas un destino para salir de la ciudad. Cycle Escape te dice hacia dónde
> pedalear para encontrar carreteras tranquilas lo antes posible."

Todo lo que se diga en la demo debe reforzar esa frase. Si una función no ayuda a
explicarla, no se muestra.

---

## 2. Reparto de voces

| Tramo | Voz principal | Apoyo |
|---|---|---|
| Problema y concepto | Javi | — |
| Demo de interfaz | Javi | — |
| Routing y Escape Point | Xián | — |
| Datos y confianza | Eva | — |
| Cierre | Javi | Equipo |

Si solo presenta una persona, el guion sigue siendo válido: se narran las tres capas.

---

## 3. Antes de empezar (checklist)

- [ ] Frontend arrancado y probado en el navegador de la demo.
- [ ] Backend arrancado y `GET /api/health` responde `ok`.
- [ ] Caché de grafo precalentada en `tmp/osm/` (no depende de Overpass en directo).
- [ ] Modo live probado con `VITE_USE_MOCK=false` en `frontend/.env`.
- [ ] Si el backend falla, fallback a mock verificado.
- [ ] Mapa con teselas cargadas (no depender del wifi del evento).
- [ ] Capturas o vídeo de respaldo por si falla la red.
- [ ] Zoom y tamaño de fuente legibles desde la última fila.
- [ ] Ninguna pestaña con secretos, tokens o consola abierta.
- [ ] Origen de demo elegido y probado.
- [ ] Cronómetro ensayado al menos una vez.

---

## 4. Guion minuto a minuto

### 0:00–0:30 — El problema

**Javi:**

> "Imagina que llegas a Santiago con la bici de carretera. No conoces la ciudad y no
> tienes un destino: solo quieres salir cuanto antes a carreteras tranquilas. Google Maps
> te pide un destino. Strava te enseña rutas de otros. Ninguno responde a la pregunta:
> **¿por qué dirección salgo?**"

> "Cycle Escape analiza la red viaria alrededor de tu posición y busca los corredores de
> escape: los puntos donde empieza una red sostenida de carreteras tranquilas."

### 0:30–1:00 — Origen y preferencias

**Javi (interacción):**

1. Hacer clic en el centro de Santiago o escribir una calle en el buscador de origen.
2. Ajustar velocidad media a 22 km/h.
3. Subir la aversión al tráfico a "Alta".
4. Mover la prioridad hacia "Menor tráfico" (aproximadamente 0.65).
5. Pulsar "Buscar salidas".

Mientras carga:

> "No pedimos destino. Pedimos punto de partida y tolerancia al tráfico."

### 1:00–2:00 — Resultado sobre el mapa

**Javi:**

> "Estos son los corredores candidatos. La ruta recomendada es la que mejor equilibra
> salir rápido y encontrar tranquilidad."

Señalar en pantalla:

1. **Escape Point**: "Este punto destacado es la puerta de salida. No es el límite de la
   ciudad: es donde empieza una red que se mantiene tranquila los siguientes kilómetros."
2. **Colores**: "Rojo es estrés alto, naranja medio-alto, amarillo transición y verde
   tranquilidad. El color sale del Road Stress de cada tramo."
3. **Métricas**: "Unos 7 minutos y 2,5 km hasta el Escape Point. QuietScore 73 después
   de salir."
4. **Alternativas**: "Suroeste, sur y noroeste quedan como opciones, pero con más tiempo
   o más tráfico."

> "Fíjate en que no decimos 'seguro' o 'inseguro'. Hablamos de estrés viario y exposición
> al tráfico. No es un safety score."

### 2:00–2:30 — Datos y confianza

**Eva (o Javi):**

> "Debajo de cada corredor mostramos de dónde salen los datos: aforos de la Xunta de
> 2024–2025, de MITMA de 2022 y tramos estimados con OpenStreetMap. En la ruta recomendada
> alrededor del 37 % del trazado tiene aforo medido; el resto se estima."

> "La regla más importante: si no hay aforo, no asumimos tráfico cero. Lo marcamos como
> estimado y bajamos la confianza. Preferimos ser honestos a inventar precisión."

### 2:30–3:00 — Cómo funciona y cierre

**Xián (o Javi):**

> "Por dentro: OpenStreetMap es el grafo base. Lo enriquecemos con los aforos, calculamos
> el Road Stress por segmento, exploramos direcciones y detectamos el primer punto con red
> sostenida tranquila."

**Javi (cierre):**

> "Cycle Escape no te lleva a un destino. Te dice por dónde empezar a pedalear. Gracias."

---

## 5. Plan B

| Fallo | Plan B |
|---|---|
| Backend caído | Cambiar a modo mock; los corredores de ejemplo siguen explicando el producto |
| Sin internet / teselas | Usar captura pregrabada del mapa y narrar sobre ella |
| Búsqueda lenta | Ya hay resultados de demo precargados en el mock |
| Error inesperado | Cambiar a la pestaña con el vídeo de respaldo y continuar |
| Pregunta que no se sabe | "Es una limitación conocida del MVP; lo tenemos anotado" |

Nunca depurar en directo más de 10 segundos. Si algo falla, se cambia al plan B y se sigue.

---

## 6. Preguntas previsibles

**¿Es un safety score?**
No. Estimamos estrés viario y exposición al tráfico con datos disponibles. No certificamos
que una carretera sea segura.

**¿De dónde salen los datos?**
OpenStreetMap para la red; Xunta de Galicia (observaciones de 2016–2025) y MITMA
(principalmente 2022) para los aforos. La interfaz muestra el año real de cada dato.

**¿Qué pasa si una carretera no tiene aforo?**
Se estima el estrés con atributos OSM, se marca como `osm_estimate` y se muestra con
confianza baja. No se interpreta como tráfico cero.

**¿Funciona fuera de Santiago?**
La arquitectura es genérica: el origen y las capas de datos son parámetros. La caché de
grafo y los datos preparados para la demo se centran en Santiago; un origen fuera de la
cobertura devuelve `OUTSIDE_COVERAGE`.

**¿Por qué no usáis Google Maps?**
Porque el problema no es llegar a un destino, sino descubrir la mejor salida. Además
necesitamos controlar el cálculo de estrés y la transparencia de los datos.

**¿Cómo elegís el Escape Point?**
No es el límite del término municipal ni la primera calle vacía: es el primer punto desde
el que la red siguiente se mantiene sostenidamente tranquila.

**¿Es navegación giro a giro?**
No. Es una herramienta de exploración y decisión; el MVP no navega.

**¿Qué falta para production?**
Más cobertura de aforos, validación con ciclistas locales, datos actualizados y evaluación
del modelo de estrés.

---

## 7. Frases que evitar

- "Es completamente seguro."
- "Garantizamos las carreteras tranquilas."
- "Sustituye a Google Maps."
- "Tenemos datos de tráfico de toda Galicia" (la cobertura es parcial).
- "El tráfico es cero" cuando no hay medición.

---

## 8. Cierre de una frase

> "Cycle Escape convierte la pregunta '¿por dónde salgo?' en una ruta visual, medible y
> honesta sobre los datos que tenemos."
