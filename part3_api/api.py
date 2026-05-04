"""
API de métricas de e-commerce sin frameworks web externos.

Provee:
  - ``get_metrics()``: función pura que filtra eventos válidos y calcula
    métricas, con soporte para filtros por país y rango de fechas.
  - ``MetricsHTTPHandler`` / ``run_server()``: servidor HTTP básico
    con ``http.server`` de la stdlib que expone ``GET /metrics``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part1_validation.validator import EventValidator
from part2_metrics.metrics import MetricsCalculator


# ======================================================================
# Función principal: get_metrics
# ======================================================================

def get_metrics(
    events: list[dict[str, Any]],
    country: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    """Filtra eventos válidos y calcula métricas de negocio.

    Flujo:
      1. Valida los eventos con ``EventValidator``.
      2. Aplica filtros opcionales de ``country`` y rango de fechas.
      3. Calcula métricas con ``MetricsCalculator``.

    Args:
        events: Lista completa de eventos (pueden incluir inválidos).
        country: Código de país para filtrar (e.g. ``"CR"``, ``"MX"``).
            Si es ``None`` no se filtra por país.
        from_date: Fecha/hora mínima en formato ISO 8601 (inclusive).
            Si es ``None`` no se aplica límite inferior.
        to_date: Fecha/hora máxima en formato ISO 8601 (inclusive).
            Si es ``None`` no se aplica límite superior.

    Returns:
        Diccionario con las métricas calculadas (misma estructura que
        ``MetricsCalculator.calculate()``), más una clave ``filters``
        que describe los filtros aplicados.
    """
    # Validar
    validator = EventValidator()
    validation = validator.validate_events(events)
    valid = validation["valid_events"]

    # Filtrar por país
    if country:
        valid = [e for e in valid if e.get("country") == country]

    # Parsear fechas de filtro
    dt_from = _parse_iso(from_date) if from_date else None
    dt_to = _parse_iso(to_date) if to_date else None

    # Filtrar por rango de fechas
    if dt_from or dt_to:
        filtered: list[dict[str, Any]] = []
        for e in valid:
            ts = _parse_iso(e.get("timestamp", ""))
            if ts is None:
                continue
            if dt_from and ts < dt_from:
                continue
            if dt_to and ts > dt_to:
                continue
            filtered.append(e)
        valid = filtered

    # Calcular métricas
    calculator = MetricsCalculator()
    metrics = calculator.calculate(valid)

    # Agregar metadatos de filtros aplicados
    metrics["filters"] = {
        "country": country,
        "from_date": from_date,
        "to_date": to_date,
    }
    metrics["events_analyzed"] = len(valid)

    return metrics


# ======================================================================
# Servidor HTTP con stdlib
# ======================================================================

# Variable global que contiene los eventos cargados para el servidor
_server_events: list[dict[str, Any]] = []


class MetricsHTTPHandler(BaseHTTPRequestHandler):
    """Handler HTTP que expone ``GET /metrics``.

    Query parameters soportados:
      - ``country``: Filtra por código de país.
      - ``from_date``: Fecha mínima (ISO 8601).
      - ``to_date``: Fecha máxima (ISO 8601).

    Responde siempre en JSON (``application/json``).
    """

    def do_GET(self) -> None:
        """Procesa solicitudes GET."""
        parsed = urlparse(self.path)

        if parsed.path != "/metrics":
            self._send_json(
                {"error": "Not Found. Use GET /metrics"}, status=404
            )
            return

        params = parse_qs(parsed.query)
        country = params.get("country", [None])[0]
        from_date = params.get("from_date", [None])[0]
        to_date = params.get("to_date", [None])[0]

        try:
            result = get_metrics(
                _server_events,
                country=country,
                from_date=from_date,
                to_date=to_date,
            )
            self._send_json(result)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(
        self, data: dict[str, Any], status: int = 200
    ) -> None:
        """Envía una respuesta JSON al cliente.

        Args:
            data: Diccionario a serializar como JSON.
            status: Código de estado HTTP.
        """
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Formato personalizado de logs del servidor."""
        print(f"  [{self.log_date_time_string()}] {format % args}")


def run_server(
    events: list[dict[str, Any]],
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Inicia el servidor HTTP de métricas.

    Args:
        events: Lista de eventos a servir.
        host: Dirección de escucha.
        port: Puerto de escucha.
    """
    global _server_events
    _server_events = events

    server = HTTPServer((host, port), MetricsHTTPHandler)
    print(f"  Servidor iniciado en http://{host}:{port}")
    print(f"  Endpoint: GET /metrics?country=CR&from_date=...&to_date=...")
    print(f"  Presiona Ctrl+C para detener.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Servidor detenido.")
    finally:
        server.server_close()


# ======================================================================
# Helpers
# ======================================================================

def _parse_iso(ts: str | None) -> datetime | None:
    """Parsea un timestamp ISO 8601 a datetime.

    Args:
        ts: Cadena ISO 8601 o None.

    Returns:
        Objeto datetime o None si el parseo falla.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ======================================================================
# Ejecución de demostración
# ======================================================================

if __name__ == "__main__":
    data_path = Path(__file__).resolve().parent.parent / "data" / "sample_events.json"

    with open(data_path, encoding="utf-8") as f:
        raw_events = json.load(f)

    # Demostración de get_metrics sin filtros
    print("=" * 60)
    print("  PART 3 - API de Metricas (sin framework)")
    print("=" * 60)

    result_all = get_metrics(raw_events)
    print("\n  >> Metricas globales (sin filtros):")
    print(f"    Revenue        : ${result_all['total_revenue']:,.2f}")
    print(f"    Purchases      : {result_all['purchases']}")
    print(f"    Unique users   : {result_all['unique_users']}")
    print(f"    Conversion rate: {result_all['conversion_rate']:.2%}")
    print(f"    Events analyzed: {result_all['events_analyzed']}")

    # Con filtro de país
    result_cr = get_metrics(raw_events, country="CR")
    print("\n  >> Metricas filtradas (country=CR):")
    print(f"    Revenue        : ${result_cr['total_revenue']:,.2f}")
    print(f"    Purchases      : {result_cr['purchases']}")
    print(f"    Unique users   : {result_cr['unique_users']}")
    print(f"    Events analyzed: {result_cr['events_analyzed']}")

    # Con filtro de rango de fechas
    result_range = get_metrics(
        raw_events,
        from_date="2026-04-30T00:00:00Z",
        to_date="2026-05-03T23:59:59Z",
    )
    print("\n  >> Metricas filtradas (2026-04-30 a 2026-05-03):")
    print(f"    Revenue        : ${result_range['total_revenue']:,.2f}")
    print(f"    Purchases      : {result_range['purchases']}")
    print(f"    Unique users   : {result_range['unique_users']}")
    print(f"    Events analyzed: {result_range['events_analyzed']}")

    # Preguntar si desea levantar el servidor HTTP
    print()
    print("  " + "-" * 56)
    answer = input("  Iniciar servidor HTTP? (s/N): ").strip().lower()
    if answer == "s":
        run_server(raw_events)
    else:
        print("  Servidor no iniciado. Fin de la demostración.\n")
