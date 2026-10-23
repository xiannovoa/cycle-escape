// Proxy serverless para Vercel.
//
// El frontend siempre llama a `/api/...`. En desarrollo, Vite reenvía esas
// peticiones a http://127.0.0.1:8000. En producción, esta función las reenvía
// a la URL pública configurada en la variable de entorno BACKEND_URL.
//
// Al ser una petición servidor-a-servidor, el navegador no necesita CORS y la
// URL real del backend no queda expuesta en el bundle del frontend.

const BACKEND_URL = (process.env.BACKEND_URL ?? '').replace(/\/+$/, '');

function errorResponse(res, status, code, message) {
  res.status(status).json({
    error: {
      code,
      message,
    },
  });
}

async function readRequestBody(req) {
  if (req.body !== undefined && req.body !== null) {
    if (Buffer.isBuffer(req.body)) return req.body;
    if (typeof req.body === 'string') return req.body;
    return JSON.stringify(req.body);
  }

  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  return chunks.length > 0 ? Buffer.concat(chunks) : undefined;
}

export default async function handler(req, res) {
  if (!BACKEND_URL) {
    errorResponse(
      res,
      500,
      'BACKEND_URL_MISSING',
      'Falta configurar la variable de entorno BACKEND_URL en Vercel.',
    );
    return;
  }

  try {
    const incomingUrl = new URL(req.url, 'http://localhost');
    const targetUrl = `${BACKEND_URL}${incomingUrl.pathname}${incomingUrl.search}`;

    const headers = {};
    if (req.headers.accept) headers.accept = req.headers.accept;
    if (req.headers['accept-language']) {
      headers['accept-language'] = req.headers['accept-language'];
    }
    if (req.headers['content-type']) {
      headers['content-type'] = req.headers['content-type'];
    }

    const hasBody = req.method !== 'GET' && req.method !== 'HEAD';
    const body = hasBody ? await readRequestBody(req) : undefined;

    const backendResponse = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
    });

    const contentType =
      backendResponse.headers.get('content-type') ?? 'application/json; charset=utf-8';
    const responseBody = await backendResponse.text();

    res.status(backendResponse.status);
    res.setHeader('content-type', contentType);
    res.setHeader('cache-control', 'no-store');
    res.send(responseBody);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Error desconocido';
    errorResponse(
      res,
      502,
      'BACKEND_UNAVAILABLE',
      `No se pudo contactar con el backend (${message}).`,
    );
  }
}

export const config = {
  maxDuration: 60,
};
