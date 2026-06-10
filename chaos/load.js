// =============================================================================
// Generador de carga para los escenarios de caos (ver chaos/README.md).
//
// A diferencia de loadtest/health.js, este script DESGLOSA las respuestas por
// código HTTP (2xx vs 503 vs otros), para que se vea con claridad cuándo el
// límite de peticiones del ingress empieza a rechazar tráfico (503).
//
// Uso:
//   docker run --rm -i --network host -e TARGET_VUS=200 -e DURATION=2m \
//     grafana/k6 run - < chaos/load.js
//
// Variables de entorno:
//   BASE_URL    URL base de la API     (default http://34.133.0.172)
//   TARGET_VUS  VUs máximos en la rampa (default 150)
//   DURATION    duración de la meseta   (default 1m)
//   TARGET_PATH ruta a golpear          (default /health)
// =============================================================================
import http from 'k6/http';
import { Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://34.133.0.172';
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || '150', 10);
const DURATION = __ENV.DURATION || '1m';
const TARGET_PATH = __ENV.TARGET_PATH || '/health';

const c2xx = new Counter('status_2xx');
const c503 = new Counter('status_503');
const cOther = new Counter('status_other');

export const options = {
  scenarios: {
    chaos: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: TARGET_VUS }, // rampa de subida (da tiempo al HPA)
        { duration: DURATION, target: TARGET_VUS }, // meseta
        { duration: '5s', target: 0 },
      ],
      gracefulRampDown: '5s',
    },
  },
  // Sin thresholds que aborten: en el escenario 2 esperamos errores a propósito.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

export default function () {
  const res = http.get(`${BASE_URL}${TARGET_PATH}`);
  if (res.status >= 200 && res.status < 300) c2xx.add(1);
  else if (res.status === 503) c503.add(1);
  else cOther.add(1);
}

export function handleSummary(data) {
  const reqs = data.metrics.http_reqs.values;
  const dur = data.metrics.http_req_duration.values;
  const ok = (data.metrics.status_2xx && data.metrics.status_2xx.values.count) || 0;
  const rejected = (data.metrics.status_503 && data.metrics.status_503.values.count) || 0;
  const other = (data.metrics.status_other && data.metrics.status_other.values.count) || 0;
  const total = reqs.count;
  const pct = (n) => (total ? ((n / total) * 100).toFixed(1) : '0.0');

  const lines = [
    '',
    `==================  CAOS — carga sobre ${TARGET_PATH}  ==================`,
    `  Requests totales : ${total}`,
    `  Throughput (R/s) : ${reqs.rate.toFixed(1)} req/s`,
    `  2xx OK           : ${ok}  (${pct(ok)} %)`,
    `  503 rechazadas   : ${rejected}  (${pct(rejected)} %)`,
    `  otros códigos    : ${other}  (${pct(other)} %)`,
    `  Latencia p95     : ${dur['p(95)'].toFixed(1)} ms`,
    `  Latencia p99     : ${dur['p(99)'].toFixed(1)} ms`,
    '====================================================================',
    '',
  ];
  return { stdout: lines.join('\n') };
}
