// =============================================================================
// Prueba de carga k6 — throughput (R/s) sobre el endpoint público /health.
//
// Mide cuántas requests/segundo aguanta la API sin tocar la base de datos ni
// servicios externos: es el "techo" del camino ingress-nginx -> Service -> pod.
//
// Uso:
//   k6 run loadtest/health.js                      # usa la IP desplegada por defecto
//   BASE_URL=http://localhost:8000 k6 run loadtest/health.js
//   TARGET_VUS=200 DURATION=1m k6 run loadtest/health.js   # override del perfil
//
// Variables de entorno:
//   BASE_URL    URL base de la API           (default http://34.133.0.172)
//   TARGET_VUS  VUs máximos en la rampa       (default 100)
//   DURATION    duración de la meseta         (default 30s)
// =============================================================================
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://34.133.0.172';
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || '100', 10);
const DURATION = __ENV.DURATION || '30s';

// Latencia propia (además de la métrica http_req_duration de k6).
const healthLatency = new Trend('health_latency', true);

export const options = {
  scenarios: {
    throughput: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '15s', target: TARGET_VUS }, // rampa de subida
        { duration: DURATION, target: TARGET_VUS }, // meseta: aquí se mide el R/s sostenido
        { duration: '5s', target: 0 }, // rampa de bajada
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'], // <1% de errores
    http_req_duration: ['p(95)<500'], // p95 < 500 ms
  },
  // p(99) no se calcula por defecto; lo pedimos para el resumen final.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

export default function () {
  const res = http.get(`${BASE_URL}/health`);
  healthLatency.add(res.timings.duration);
  check(res, {
    'status 200': (r) => r.status === 200,
    'body status ok': (r) => r.json('status') === 'ok',
  });
}

// Resumen final centrado en R/s.
export function handleSummary(data) {
  const reqs = data.metrics.http_reqs.values;
  const dur = data.metrics.http_req_duration.values;
  const failed = data.metrics.http_req_failed.values;

  const lines = [
    '',
    '====================  RESULTADO (throughput /health)  ====================',
    `  Requests totales : ${reqs.count}`,
    `  Throughput (R/s) : ${reqs.rate.toFixed(1)} req/s`,
    `  Errores          : ${(failed.rate * 100).toFixed(2)} %`,
    `  Latencia  avg    : ${dur.avg.toFixed(1)} ms`,
    `  Latencia  p95    : ${dur['p(95)'].toFixed(1)} ms`,
    `  Latencia  p99    : ${dur['p(99)'].toFixed(1)} ms`,
    `  Latencia  max    : ${dur.max.toFixed(1)} ms`,
    '==========================================================================',
    '',
  ];
  return { stdout: lines.join('\n') };
}
