"""
Módulo de cálculo de métricas sobre eventos de e-commerce.

Opera exclusivamente sobre eventos **válidos** (ya filtrados por el
validador) y produce indicadores clave de negocio.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

# Importación relativa al proyecto — funciona al ejecutar como módulo o script
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from part1_validation.validator import EventValidator


class MetricsCalculator:
    """Calculador de métricas de negocio para eventos de e-commerce.

    Todas las métricas se calculan sobre la lista de eventos proporcionada,
    que se asume ya validada y libre de duplicados.
    """

    def calculate(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Calcula métricas de negocio a partir de eventos válidos.

        Args:
            events: Lista de eventos válidos (sin duplicados ni errores).

        Returns:
            Diccionario con las siguientes claves:
              - ``total_revenue`` (float): Suma de ``price`` en eventos
                de tipo ``purchase``.
              - ``purchases`` (int): Cantidad de eventos ``purchase``.
              - ``unique_users`` (int): Cantidad de ``user_id`` únicos
                en todos los eventos.
              - ``conversion_rate`` (float): Proporción de usuarios que
                realizaron al menos un ``purchase`` sobre los usuarios que
                realizaron al menos un ``product_view`` (valor entre 0 y 1).
              - ``top_products`` (list[dict]): Top 5 ``product_id`` por
                frecuencia de aparición (cualquier tipo de evento).  Cada
                elemento es ``{"product_id": str, "count": int}``.
        """
        purchases = [e for e in events if e["event_type"] == "purchase"]
        total_revenue = sum(e.get("price", 0) for e in purchases)

        # Usuarios únicos globales
        all_users = {e["user_id"] for e in events}

        # Usuarios que hicieron product_view
        viewers = {
            e["user_id"] for e in events if e["event_type"] == "product_view"
        }

        # Usuarios que hicieron purchase
        buyers = {e["user_id"] for e in purchases}

        # Tasa de conversión: compradores / viewers
        conversion_rate = (
            len(buyers) / len(viewers) if viewers else 0.0
        )

        # Top 5 productos por frecuencia (cualquier tipo de evento)
        product_counter: Counter[str] = Counter(
            e["product_id"] for e in events if e.get("product_id")
        )
        top_products = [
            {"product_id": pid, "count": count}
            for pid, count in product_counter.most_common(5)
        ]

        return {
            "total_revenue": round(total_revenue, 2),
            "purchases": len(purchases),
            "unique_users": len(all_users),
            "conversion_rate": round(conversion_rate, 4),
            "top_products": top_products,
        }


# ======================================================================
# Ejecución de demostración
# ======================================================================

if __name__ == "__main__":
    data_path = Path(__file__).resolve().parent.parent / "data" / "sample_events.json"

    with open(data_path, encoding="utf-8") as f:
        raw_events = json.load(f)

    # Paso 1: Validar
    validator = EventValidator()
    validation = validator.validate_events(raw_events)
    valid_events = validation["valid_events"]

    # Paso 2: Calcular métricas
    calculator = MetricsCalculator()
    metrics = calculator.calculate(valid_events)

    print("=" * 60)
    print("  PART 2 - Metricas de Negocio")
    print("=" * 60)
    print(f"  Total revenue    : ${metrics['total_revenue']:,.2f}")
    print(f"  Purchases        : {metrics['purchases']}")
    print(f"  Unique users     : {metrics['unique_users']}")
    print(f"  Conversion rate  : {metrics['conversion_rate']:.2%}")
    print()
    print("  Top 5 productos:")
    for i, p in enumerate(metrics["top_products"], 1):
        print(f"    {i}. {p['product_id']} - {p['count']} eventos")
    print()
