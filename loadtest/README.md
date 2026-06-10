# Pruebas de carga (k6)

Mide el **throughput (requests/segundo)** y la latencia de la API SIPScan
desplegada en GKE, usando [k6](https://k6.io).

## Scripts

| Script | Endpoint | Auth | Qué mide |
|---|---|---|---|
| `health.js` | `GET /health` | No | Techo de throughput del camino ingress → pod (sin DB). |
| `api_read.js` | `GET /metadata/receipt-statuses` | Sí (JWT) | R/s de un read real contra PostgreSQL. |

## Instalar k6

```bash
# Debian/Ubuntu
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6

# o con Docker, sin instalar nada:
#   docker run --rm -i grafana/k6 run - < loadtest/health.js
```

## Ejecutar

```bash
# Throughput puro (usa la IP desplegada por defecto: http://34.133.0.172)
k6 run loadtest/health.js

# Subir la carga: 300 VUs durante 1 minuto de meseta
TARGET_VUS=300 DURATION=1m k6 run loadtest/health.js

# Read autenticado (AUTH_SECRET debe ser el mismo de k8s/secret.yaml)
AUTH_SECRET="$(grep AUTH_SECRET ../k8s/secret.yaml | head -1 | awk '{print $2}' | tr -d '\"')" \
  k6 run loadtest/api_read.js
```

### Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `BASE_URL` | `http://34.133.0.172` | URL base de la API. |
| `TARGET_VUS` | `100` (health) / `50` (read) | VUs máximos en la rampa. |
| `DURATION` | `30s` | Duración de la meseta donde se mide el R/s sostenido. |
| `AUTH_SECRET` | — | (solo `api_read.js`) secreto JWT HS256. |

## Cómo leer el resultado

Cada script imprime un resumen al final, p. ej.:

```
====================  RESULTADO (throughput /health)  ====================
  Requests totales : 124500
  Throughput (R/s) : 4150.0 req/s
  Errores          : 0.00 %
  Latencia  p95    : 38.2 ms
==========================================================================
```

- **Throughput (R/s)** es la métrica pedida: requests servidas por segundo
  durante toda la prueba.
- Sube `TARGET_VUS` hasta que la latencia p95 empiece a dispararse o aparezcan
  errores: ese es el punto donde el cluster se satura (y donde el HPA debería
  escalar las réplicas de `sipscan-api`).

> El perfil arranca conservador para no tumbar el cluster del amigo. Auméntalo
> de forma gradual.
