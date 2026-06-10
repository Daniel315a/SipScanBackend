# Escenarios de caos — SIPScan

Tres escenarios reproducibles para demostrar resiliencia y límites de la API
desplegada en GKE. La "palanca" del caos es el **límite de peticiones del
ingress** (`nginx.ingress.kubernetes.io/limit-rps`): un máximo de requests/seg
que puedes subir o bajar **en caliente**, sin redeploy.

| Escenario | Qué demuestra | Resultado esperado |
|---|---|---|
| 1 | Camino feliz + autoescalado | Bajo carga, el HPA sube los pods (1 → 3), ~100 % 2xx |
| 2 | La app se "cae" por el límite máximo de peticiones | nginx devuelve **503**, la R/s se corta |
| 3 | Subo el límite y la app vuelve | ~100 % 2xx de nuevo |

## Requisitos

- `kubectl` apuntando al cluster `sip-scan` (ya configurado).
- Docker (para correr k6 sin instalarlo).
- El generador de carga: [chaos/load.js](load.js) (desglosa respuestas 2xx vs 503).

> **Tip:** usa **dos terminales**. En una, el observador en vivo:
> ```bash
> watch -n 2 kubectl get hpa,pods -n sipscan
> ```
> En la otra, lanzas la carga de cada escenario.

---

## Escenario 1 — Todo bien: la carga eleva los pods

**Estado de partida:** sin límite en el ingress (estado normal).

```bash
# (asegurar que no hay límite)
kubectl annotate ingress sipscan-api -n sipscan nginx.ingress.kubernetes.io/limit-rps- 2>/dev/null

# Carga sostenida 3 min para que el HPA reaccione
docker run --rm -i --network host -e TARGET_VUS=150 -e DURATION=3m \
  grafana/k6 run - < chaos/load.js
```

**Qué observar** (en la terminal del `watch`):
- El `TARGETS` del HPA cruza el 70 % de CPU.
- `REPLICAS` sube **1 → 2 → 3** y aparecen nuevos pods `sipscan-api` `Running`.
- En el resumen de k6: **2xx ≈ 100 %**, 503 = 0.
- Al terminar la carga, el HPA baja solo a 1 en ~2 min (config de `behavior`).

> El sistema absorbe el pico **añadiendo capacidad**. Tope = 3 pods (cabe en los
> 3 nodos `e2-medium`).

---

## Escenario 2 — La app se cae por el límite máximo de peticiones

Ponemos un límite **muy bajo** de peticiones. nginx rechazará todo lo que pase
de ahí con **HTTP 503** antes de que llegue a los pods.

```bash
# Límite máximo = 10 req/s por IP cliente
kubectl annotate ingress sipscan-api -n sipscan \
  nginx.ingress.kubernetes.io/limit-rps="10" --overwrite

sleep 8   # nginx recarga la config

# Misma carga que antes
docker run --rm -i --network host -e TARGET_VUS=150 -e DURATION=1m \
  grafana/k6 run - < chaos/load.js
```

**Qué observar:**
- En el resumen de k6: la gran mayoría son **503 rechazadas** (en pruebas: ~97 %).
- El `Throughput (R/s)` efectivo de 2xx se desploma al tope del límite.
- Los pods **no** se reinician ni escalan: el tráfico ni siquiera llega a la app
  (nginx corta antes). Desde fuera, "la app no responde".

> Verificar el límite activo:
> ```bash
> kubectl get ingress sipscan-api -n sipscan \
>   -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/limit-rps}'; echo
> ```

---

## Escenario 3 — Subo el límite y la app vuelve a funcionar

Hay **dos formas** de cambiar el límite máximo (elige una):

**A) Subirlo a un valor alto** (sigue habiendo protección, pero holgada):
```bash
kubectl annotate ingress sipscan-api -n sipscan \
  nginx.ingress.kubernetes.io/limit-rps="1000" --overwrite
```

**B) Quitarlo por completo** (sin límite):
```bash
kubectl annotate ingress sipscan-api -n sipscan nginx.ingress.kubernetes.io/limit-rps-
```

Luego:
```bash
sleep 8   # nginx recarga la config

docker run --rm -i --network host -e TARGET_VUS=150 -e DURATION=1m \
  grafana/k6 run - < chaos/load.js
```

**Qué observar:**
- En el resumen de k6: **2xx vuelve a ~100 %**, 503 = 0.
- La API responde con normalidad; si la carga es alta, vuelve a entrar el
  autoescalado del Escenario 1.

> El "cambio del límite máximo" es esa anotación `limit-rps`. Es el botón que
> apaga/enciende el caos del Escenario 2.

---

## Reset (volver al estado limpio)

```bash
# Quitar cualquier límite
kubectl annotate ingress sipscan-api -n sipscan nginx.ingress.kubernetes.io/limit-rps- 2>/dev/null

# Forzar 1 réplica si quedó escalado
kubectl scale deploy/sipscan-api --replicas=1 -n sipscan

# Comprobar salud
curl -s http://34.133.0.172/health; echo
```

## Notas

- `limit-rps` se aplica **por IP de cliente** (nginx usa `limit_req`). Con k6
  desde una sola máquina, toda la carga cuenta como un cliente, por eso el límite
  se dispara fácil. nginx además permite ráfagas hasta `limit-rps ×
  limit-burst-multiplier` (multiplicador por defecto = 5) antes de empezar a
  devolver 503.
- El 503 del Escenario 2 es nginx **protegiendo** la app (control de admisión),
  no un crash del backend. Es el comportamiento *deseable* frente a sobrecarga:
  mejor rechazar limpio con 503 que dejar que la app se degrade o caiga.
- Variables del generador de carga ([load.js](load.js)): `BASE_URL`,
  `TARGET_VUS`, `DURATION`, `TARGET_PATH` (default `/health`).
