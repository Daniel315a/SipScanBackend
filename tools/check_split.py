#!/usr/bin/env python3
"""Prueba la distribución de tráfico entre el track STABLE y el CANARY.

Golpea el endpoint /health a través del Ingress varias veces y clasifica cada
respuesta según la versión que devuelve la app:

  - STABLE  -> {"status": "ok",     "version": "1.0.0", ...}
  - CANARY  -> {"status": "canary", "version": "2.1.0-canary", ...}

Muestra en consola el conteo, el porcentaje real y una barra comparada con el
peso esperado del canary.

Uso:
    python3 tools/check_split.py                       # IP por defecto, 100 reqs
    python3 tools/check_split.py --ip 34.172.32.213 -n 200
    python3 tools/check_split.py --url http://mi-host/health -n 500 --expected 10

Solo usa la librería estándar (no requiere instalar nada).
"""
import argparse
import json
import sys
import urllib.request
from collections import Counter

DEFAULT_IP = "34.172.32.213"

# Códigos de color ANSI (se desactivan si la salida no es una terminal)
class C:
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def _no_color():
    C.GREEN = C.YELLOW = C.RED = C.BOLD = C.DIM = C.RESET = ""


def classify(payload: dict) -> str:
    """Devuelve 'CANARY', 'STABLE' o 'UNKNOWN' a partir del JSON de /health."""
    version = str(payload.get("version", ""))
    status = str(payload.get("status", ""))
    if version.endswith("canary") or status == "canary":
        return "CANARY"
    if status in ("ok", "degraded") or version:
        return "STABLE"
    return "UNKNOWN"


def hit(url: str, timeout: float):
    """Devuelve (track, detalle) donde detalle es la respuesta cruda o el error."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8").strip()
            if resp.status != 200:
                return f"HTTP_{resp.status}", body[:200]
            data = json.loads(body)
            return classify(data), json.dumps(data, ensure_ascii=False, sort_keys=True)
    except Exception as exc:  # noqa: BLE001 - queremos contar cualquier fallo
        return f"ERROR:{type(exc).__name__}", str(exc)[:200]


def bar(pct: float, width: int = 40) -> str:
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def main() -> int:
    ap = argparse.ArgumentParser(description="Prueba la distribución stable/canary.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--ip", default=None, help=f"IP del Ingress (default {DEFAULT_IP})")
    g.add_argument("--url", default=None, help="URL completa del endpoint /health")
    ap.add_argument("-n", "--requests", type=int, default=100, help="Número de peticiones (default 100)")
    ap.add_argument("--path", default="/health", help="Ruta a consultar (default /health)")
    ap.add_argument("--expected", type=float, default=10.0, help="%% canary esperado (default 10)")
    ap.add_argument("--timeout", type=float, default=8.0, help="Timeout por petición en segundos")
    ap.add_argument("--no-color", action="store_true", help="Desactiva colores")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="No imprime cada respuesta, solo el resumen final")
    args = ap.parse_args()

    if args.no_color or not sys.stdout.isatty():
        _no_color()

    if args.url:
        url = args.url
    else:
        ip = args.ip or DEFAULT_IP
        url = f"http://{ip}{args.path}"

    print(f"{C.BOLD}Probando distribución de tráfico{C.RESET}")
    print(f"  Endpoint : {url}")
    print(f"  Peticiones: {args.requests}")
    print(f"  Canary esperado: {args.expected:.0f}%\n")

    color_of = {"STABLE": C.GREEN, "CANARY": C.YELLOW}
    width = len(str(args.requests))

    counts: Counter = Counter()
    for i in range(1, args.requests + 1):
        track, detail = hit(url, args.timeout)
        counts[track] += 1
        if not args.quiet:
            col = color_of.get(track, C.RED)
            label = track if track in color_of else "ERROR"
            print(f"  #{i:>{width}}  {col}{label:<7}{C.RESET}{C.DIM}{detail}{C.RESET}")
    if not args.quiet:
        print()

    total = sum(counts.values())
    stable = counts.get("STABLE", 0)
    canary = counts.get("CANARY", 0)
    errors = {k: v for k, v in counts.items() if k not in ("STABLE", "CANARY")}

    def pct(x: int) -> float:
        return (x / total * 100) if total else 0.0

    print(f"{C.BOLD}Resultados{C.RESET}  (total={total})")
    print("─" * 60)
    print(f"  {C.GREEN}STABLE{C.RESET}  {stable:4d}  {pct(stable):5.1f}%  {C.GREEN}{bar(pct(stable))}{C.RESET}")
    print(f"  {C.YELLOW}CANARY{C.RESET}  {canary:4d}  {pct(canary):5.1f}%  {C.YELLOW}{bar(pct(canary))}{C.RESET}")
    if errors:
        err_total = sum(errors.values())
        print(f"  {C.RED}ERROR {C.RESET}  {err_total:4d}  {pct(err_total):5.1f}%  -> {dict(errors)}")
    print("─" * 60)

    # Veredicto sencillo: ¿el canary cae dentro de ±50% relativo del esperado?
    if total and (stable or canary):
        target = args.expected
        low, high = target * 0.5, target * 1.5
        actual = pct(canary)
        if low <= actual <= high:
            print(f"  {C.GREEN}✓ Distribución coherente con el ~{target:.0f}% esperado "
                  f"(canary real {actual:.1f}%).{C.RESET}")
        else:
            print(f"  {C.YELLOW}⚠ Canary real {actual:.1f}% fuera del rango esperado "
                  f"({low:.0f}–{high:.0f}%). Aumenta -n para reducir el ruido estadístico.{C.RESET}")
    if errors:
        print(f"  {C.RED}⚠ Hubo errores de red/HTTP; revisa el Ingress y los pods.{C.RESET}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
