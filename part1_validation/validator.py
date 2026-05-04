"""
Módulo de validación de eventos de e-commerce.

Proporciona la clase EventValidator que verifica la integridad y validez
de eventos de e-commerce según reglas de negocio definidas.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Tipos de evento permitidos en el sistema
VALID_EVENT_TYPES = {"product_view", "add_to_cart", "purchase"}


class EventValidator:
    """Validador de eventos de e-commerce.

    Aplica las siguientes reglas de validación a cada evento:
      - ``event_id`` requerido (no vacío).
      - ``user_id`` requerido (no vacío).
      - ``event_type`` debe ser uno de: product_view, add_to_cart, purchase.
      - ``timestamp`` debe ser una cadena ISO 8601 válida.
      - Si ``event_type`` es ``purchase``, ``price`` debe ser > 0.
      - Detección de duplicados por ``event_id``.
    """

    def validate_events(
        self, events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Valida una lista de eventos y retorna un resumen de resultados.

        Args:
            events: Lista de diccionarios, cada uno representando un evento.

        Returns:
            Diccionario con las claves:
              - ``total_events`` (int): Total de eventos recibidos.
              - ``valid_events`` (list[dict]): Eventos que pasaron todas las
                validaciones y no son duplicados.
              - ``invalid_events`` (list[dict]): Eventos que fallaron al menos
                una validación.  Cada entrada incluye la clave ``_errors``
                con la lista de errores encontrados.
              - ``duplicated_events`` (list[str]): ``event_id`` de eventos
                que aparecen más de una vez (solo los repetidos).
        """
        seen_ids: dict[str, int] = {}
        valid: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []

        for event in events:
            errors = self._validate_single(event)

            # Rastrear duplicados por event_id
            eid = event.get("event_id", "")
            if eid:
                seen_ids[eid] = seen_ids.get(eid, 0) + 1

            if errors:
                event_copy = {**event, "_errors": errors}
                invalid.append(event_copy)
            else:
                valid.append(event)

        # Detectar event_ids duplicados
        duplicated_ids = sorted(
            eid for eid, count in seen_ids.items() if count > 1
        )

        # Remover la segunda (o posterior) aparición de duplicados de válidos
        first_seen: set[str] = set()
        deduplicated_valid: list[dict[str, Any]] = []
        for event in valid:
            eid = event["event_id"]
            if eid in first_seen:
                # Mover duplicado a inválidos con su error
                event_copy = {**event, "_errors": ["Evento duplicado"]}
                invalid.append(event_copy)
            else:
                first_seen.add(eid)
                deduplicated_valid.append(event)

        return {
            "total_events": len(events),
            "valid_events": deduplicated_valid,
            "invalid_events": invalid,
            "duplicated_events": duplicated_ids,
        }

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    def _validate_single(self, event: dict[str, Any]) -> list[str]:
        """Valida un evento individual y retorna la lista de errores.

        Args:
            event: Diccionario con los datos del evento.

        Returns:
            Lista de cadenas describiendo cada error encontrado.
            Lista vacía si el evento es válido.
        """
        errors: list[str] = []

        # event_id requerido
        if not event.get("event_id"):
            errors.append("event_id es requerido")

        # user_id requerido
        if not event.get("user_id"):
            errors.append("user_id es requerido")

        # event_type válido
        event_type = event.get("event_type", "")
        if event_type not in VALID_EVENT_TYPES:
            errors.append(
                f"event_type invalido: '{event_type}'. "
                f"Debe ser uno de {sorted(VALID_EVENT_TYPES)}"
            )

        # timestamp ISO 8601
        ts = event.get("timestamp", "")
        if not self._is_valid_iso_timestamp(ts):
            errors.append(f"timestamp invalido: '{ts}'")

        # Si es purchase, price > 0
        if event_type == "purchase":
            price = event.get("price", 0)
            if not isinstance(price, (int, float)) or price <= 0:
                errors.append(
                    f"price debe ser > 0 para purchases, recibido: {price}"
                )

        return errors

    @staticmethod
    def _is_valid_iso_timestamp(ts: str) -> bool:
        """Verifica si una cadena es un timestamp ISO 8601 válido.

        Args:
            ts: Cadena a verificar.

        Returns:
            True si es un timestamp ISO 8601 válido, False en caso contrario.
        """
        if not ts:
            return False
        try:
            # Soporta formatos con y sin 'Z'
            cleaned = ts.replace("Z", "+00:00")
            datetime.fromisoformat(cleaned)
            return True
        except (ValueError, TypeError):
            return False


# ======================================================================
# Ejecución de demostración
# ======================================================================

if __name__ == "__main__":
    data_path = Path(__file__).resolve().parent.parent / "data" / "sample_events.json"

    with open(data_path, encoding="utf-8") as f:
        raw_events = json.load(f)

    validator = EventValidator()
    result = validator.validate_events(raw_events)

    print("=" * 60)
    print("  PART 1 - Validacion de Eventos")
    print("=" * 60)
    print(f"  Total de eventos recibidos : {result['total_events']}")
    print(f"  Eventos validos            : {len(result['valid_events'])}")
    print(f"  Eventos invalidos          : {len(result['invalid_events'])}")
    print(f"  IDs duplicados             : {result['duplicated_events']}")
    print()

    if result["invalid_events"]:
        print("  Detalle de eventos invalidos:")
        print("  " + "-" * 56)
        for evt in result["invalid_events"]:
            eid = evt.get("event_id", "(sin id)")
            print(f"    - {eid}: {evt['_errors']}")
    print()
