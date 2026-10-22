# Despliegue en Vercel

Esta guía deja el **frontend** de Cyclout publicado en Vercel y conectado a la API real.

> **Vercel solo aloja el frontend y un proxy serverless.** El backend FastAPI/OSMnx debe
> estar desplegado y accesible públicamente en otro sitio (Render, Railway, Fly.io, un VPS
> o un túnel estable). Sin un backend público, la demo en otro ordenador no puede funcionar.

## Arquitectura

```text
Navegador
   │
   ├── https://cyclout.vercel.app          → frontend estático (Vite)
   │
   └── https://cyclout.vercel.app/api/...  → función serverless de Vercel
                                                │
                                                └── BACKEND_URL/api/...
                                                    (Render, Railway, Fly, VPS...)
```

La función `frontend/api/[...path].js` reenvía cualquier petición `/api/*` al backend. Al
hacerlo desde el servidor:

- el navegador no necesita CORS;
- la URL real del backend no se incluye en el bundle del frontend;
- el frontend sigue usando rutas relativas (`/api/escape-routes`), igual que en desarrollo.

## Requisitos

- Cuenta gratuita en [Vercel](https://vercel.com).
- Repositorio `xiannovoa/cycle-escape` en GitHub.
- Node.js 20 o superior y npm (para la CLI).
- Backend público con HTTPS y el endpoint `POST /api/escape-routes`.
- Grafo OSM y datos de tráfico disponibles en el backend desplegado.

## 1. Publicar el backend primero

El backend no forma parte de este despliegue. Xián debe publicarlo en un servicio con
Python, por ejemplo:

- **Render** (Web Service).
- **Railway**.
- **Fly.io**.
- **VPS** con Docker.

No se recomienda desplegar el backend como función serverless de Vercel: OSMnx, GeoPandas,
el grafo cacheado y los datos de tráfico no encajan bien con el tamaño, el arranque en frío
y el sistema de ficheros efímero de las funciones.

Comprueba que responde:

```powershell
curl.exe https://tu-backend-publico/api/health
```

Debe devolver JSON del backend, no una página HTML de error. La URL que usarás como
`BACKEND_URL` es la base, **sin** `/api` al final:

```text
https://tu-backend-publico
```

La aplicación llama a:

```text
POST https://tu-backend-publico/api/escape-routes
```

Si el backend solo escucha en `127.0.0.1`, no sirve para una demo en otro ordenador. Para
una demo con el portátil encendido se puede usar un túnel de Cloudflare, pero la URL debe
ser estable y el portátil debe seguir conectado durante toda la presentación.

## 2. Desplegar el frontend desde la web de Vercel

1. Entra en Vercel y pulsa **Add New → Project**.
2. Importa `xiannovoa/cycle-escape`.
3. Configura el proyecto:

   | Ajuste | Valor |
   |---|---|
   | Root Directory | `frontend` |
   | Framework Preset | `Vite` |
   | Build Command | `npm run build` |
   | Output Directory | `dist` |
   | Install Command | `npm install` |

4. En **Environment Variables**, añade:

   | Variable | Valor | Entornos |
   |---|---|---|
   | `BACKEND_URL` | `https://tu-backend-publico` | Production, Preview |

   No lleva prefijo `VITE_`: es una variable de servidor y no se expone al navegador.

5. Pulsa **Deploy**.

`frontend/vercel.json` ya define el framework, el build, `dist` y la duración máxima de la
función proxy.

> Si antes configuraste `VITE_API_URL` en Vercel, bórrala para usar el proxy. Si se deja,
> el frontend llamará directamente al backend y necesitará CORS.

## 3. Desplegar con la CLI

```powershell
npm install -g vercel
vercel login

cd C:\Users\jcord\IA\IA_cuarto\Hackaton\cycle-escape\frontend
vercel
```

La primera vez crearás o enlazarás el proyecto. Después añade la URL del backend:

```powershell
vercel env add BACKEND_URL production
# Pega https://tu-backend-publico cuando lo pida

vercel env add BACKEND_URL preview
# Pega la misma URL
```

Despliega a producción:

```powershell
vercel --prod
```

Vercel imprimirá la URL final, por ejemplo:

```text
https://cycle-escape-xxxx.vercel.app
```

## 4. Verificar el despliegue

1. Abre la URL de Vercel en el navegador.
2. Comprueba que el mapa carga y que aparece el onboarding.
3. Abre la consola de red del navegador y verifica que las peticiones van a
   `https://tu-app.vercel.app/api/...`.
4. Prueba el proxy directamente:

   ```powershell
   curl.exe https://tu-app.vercel.app/api/health
   ```

   Debe devolver la respuesta del backend. Si devuelve un 404 HTML de Vercel, la función
   proxy no se ha desplegado o el Root Directory no es `frontend`.
5. Haz doble clic en el mapa y comprueba que aparecen las rutas.

## 5. Lanzar la demo en otro ordenador

1. Confirma que el backend público está despierto y responde en `/api/health`.
2. Abre la URL de Vercel en el ordenador de la demo.
3. Si es la primera vez, completa el onboarding: nombre, velocidad y preferencia.
4. Haz doble clic en el mapa para fijar el origen (o busca una calle).
5. Espera las rutas y selecciona una para ver el detalle.
6. Si el backend gratuito se duerme, haz una petición de calentamiento antes de empezar.
7. Ten preparado un vídeo o capturas por si falla la red de la sala.

La demo **no depende de tu ordenador** si el backend está en la nube. Si el backend corre
en tu portátil o detrás de un túnel, tu portátil sí debe estar encendido y conectado.

## Variables de entorno

| Variable | Dónde se usa | ¿Se expone al navegador? |
|---|---|---|
| `BACKEND_URL` | Función serverless de Vercel | No |
| `VITE_API_URL` | Build del frontend, modo directo | Sí |

Con el proxy configurado, deja `VITE_API_URL` sin definir. Si usas el modo directo, el
backend debe permitir CORS desde el dominio de Vercel y deberás redesplegar después de
cambiar la variable (Vite la inyecta en tiempo de build).

## Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `BACKEND_URL_MISSING` | Falta la variable en Vercel | Añadir `BACKEND_URL` y redesplegar |
| `502 BACKEND_UNAVAILABLE` | Backend caído, URL mal o sin HTTPS | Probar la URL con `curl` |
| 404 HTML en `/api/...` | La función proxy no se desplegó | Revisar Root Directory y que exista `frontend/api/[...path].js` |
| La búsqueda tarda y falla | Backend dormido o arranque en frío | Calentar `/api/health` antes de la demo |
| CORS bloqueado | Se está usando `VITE_API_URL` directo | Quitar la variable o añadir el dominio al backend |
| El mapa carga pero no hay rutas | Backend sin grafo/datos o sin cobertura | Revisar logs del backend |
| Cambio de variable sin efecto | Vercel no ha redesplegado | Ejecutar `vercel --prod` de nuevo |

> El cliente aborta la búsqueda a los 6,5 segundos. Un backend dormido puede tardar más en
> arrancar, así que conviene calentarlo antes de la demo.

## Notas

- La función proxy tiene `maxDuration: 60` segundos, pero el límite efectivo depende del
  plan de Vercel.
- No se guardan secretos en el repositorio. `BACKEND_URL` se configura en Vercel.
- El frontend no incluye datos de prueba: si el backend no responde, muestra un error.
