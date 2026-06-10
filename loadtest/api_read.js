// =============================================================================
// Prueba de carga k6 — R/s sobre un endpoint AUTENTICADO de solo lectura:
//   GET /metadata/receipt-statuses   (lee de PostgreSQL, requiere Bearer JWT)
//
// Mide el throughput de un read real (API + DB), más representativo que /health.
// El JWT se genera dentro del propio script con HS256 a partir de AUTH_SECRET,
// replicando el esquema del backend (campo personalizado "fin" = expiración ISO).
//
// Uso:
//   AUTH_SECRET=... k6 run loadtest/api_read.js
//   BASE_URL=http://localhost:8000 AUTH_SECRET=... TARGET_VUS=50 k6 run loadtest/api_read.js
//
// Variables de entorno:
//   BASE_URL     URL base de la API          (default http://34.133.0.172)
//   AUTH_SECRET  secreto JWT (HS256)         (OBLIGATORIO; igual al del Secret k8s)
//   TARGET_VUS   VUs máximos                 (default 50)
//   DURATION     duración de la meseta       (default 30s)
// =============================================================================
import http from 'k6/http';
import { check } from 'k6';
import crypto from 'k6/crypto';
import encoding from 'k6/encoding';

const BASE_URL = __ENV.BASE_URL || 'http://34.133.0.172';
const AUTH_SECRET = __ENV.AUTH_SECRET;
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || '50', 10);
const DURATION = __ENV.DURATION || '30s';

if (!AUTH_SECRET) {
  throw new Error('Falta AUTH_SECRET (el mismo valor que en k8s/secret.yaml).');
}

// Construye un JWT HS256 con el campo "fin" (expiración) que valida el backend.
function makeJWT(secret) {
  const header = encoding.b64encode(
    JSON.stringify({ alg: 'HS256', typ: 'JWT' }),
    'rawurl'
  );
  const fin = new Date(Date.now() + 3600 * 1000).toISOString(); // +1 hora
  const payload = encoding.b64encode(JSON.stringify({ fin }), 'rawurl');
  const signingInput = `${header}.${payload}`;
  const signature = crypto.hmac('sha256', secret, signingInput, 'base64rawurl');
  return `${signingInput}.${signature}`;
}

// Un único token reutilizado por todos los VUs (se calcula una vez en init).
const TOKEN = makeJWT(AUTH_SECRET);

export const options = {
  scenarios: {
    read_throughput: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '15s', target: TARGET_VUS },
        { duration: DURATION, target: TARGET_VUS },
        { duration: '5s', target: 0 },
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'], // el read pega a la DB: umbral algo mayor
  },
  // p(99) no se calcula por defecto; lo pedimos para el resumen final.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

const params = {
  headers: {
    Authorization: `Bearer ${TOKEN}`,
    Accept: 'application/json',
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/metadata/receipt-statuses`, params);
  check(res, {
    'status 200': (r) => r.status === 200,
    'es lista JSON': (r) => Array.isArray(r.json()),
  });
}

export function handleSummary(data) {
  const reqs = data.metrics.http_reqs.values;
  const dur = data.metrics.http_req_duration.values;
  const failed = data.metrics.http_req_failed.values;

  const lines = [
    '',
    '=============  RESULTADO (read autenticado /metadata/receipt-statuses)  =============',
    `  Requests totales : ${reqs.count}`,
    `  Throughput (R/s) : ${reqs.rate.toFixed(1)} req/s`,
    `  Errores          : ${(failed.rate * 100).toFixed(2)} %`,
    `  Latencia  avg    : ${dur.avg.toFixed(1)} ms`,
    `  Latencia  p95    : ${dur['p(95)'].toFixed(1)} ms`,
    `  Latencia  p99    : ${dur['p(99)'].toFixed(1)} ms`,
    `  Latencia  max    : ${dur.max.toFixed(1)} ms`,
    '====================================================================================',
    '',
  ];
  return { stdout: lines.join('\n') };
}
