# E-commerce Real-Time Analytics Pipeline

Pipeline de procesamiento de eventos de e-commerce en tiempo real, implementado
en Python 3.10+ puro (sin dependencias externas).

## Descripción

Este proyecto implementa un sistema completo de procesamiento de eventos de
e-commerce que abarca cuatro áreas:

1. **Validación de datos** — Verificación de integridad y detección de duplicados.
2. **Cálculo de métricas** — Indicadores clave de negocio (revenue, conversión, etc.).
3. **API sin framework** — Endpoint HTTP funcional usando solo `http.server` de stdlib.
4. **Diseño en Tinybird** — Arquitectura propuesta para producción con ClickHouse.

## Estructura del Proyecto

```
python-tinybird-challenge/
├── README.md                       # Este archivo
├── requirements.txt                # Sin dependencias externas (solo stdlib)
├── data/
│   └── sample_events.json          # Dataset de prueba (~24 eventos)
├── part1_validation/
│   └── validator.py                # Clase EventValidator
├── part2_metrics/
│   └── metrics.py                  # Clase MetricsCalculator
├── part3_api/
│   └── api.py                      # Función get_metrics + servidor HTTP
└── part4_design/
    └── DESIGN.md                   # Documento de diseño para Tinybird
```

## Requisitos

- **Python 3.10+** (se usan type hints con `X | Y` y `match` statements)
- Sin dependencias externas

## Cómo Ejecutar

### Part 1 — Validación de Eventos

```bash
python part1_validation/validator.py  
```

**Output esperado:**

```
============================================================
  PART 1 — Validación de Eventos
============================================================
  Total de eventos recibidos : 24
  Eventos válidos            : 16
  Eventos inválidos          : 8
  IDs duplicados             : ['evt_003', 'evt_007']

  Detalle de eventos inválidos:
  --------------------------------------------------------
    • evt_017: ['price debe ser > 0 para purchases, recibido: 0']
    • evt_018: ["event_type inválido: 'invalid_event'. ..."]
    • (sin id): ['event_id es requerido']
    • evt_020: ['user_id es requerido']
    • evt_021: ["timestamp inválido: 'not-a-date'"]
    • evt_003: ['Evento duplicado']
    • evt_007: ['Evento duplicado']
```

### Part 2 — Métricas de Negocio

```bash
python part2_metrics/metrics.py
```

**Output esperado:**

```
============================================================
  PART 2 — Métricas de Negocio
============================================================
  Total revenue    : $209.48
  Purchases        : 3
  Unique users     : 7
  Conversion rate  : 42.86%

  Top 5 productos:
    1. p_10 — 7 eventos
    2. p_30 — 3 eventos
    3. p_20 — 2 eventos
    4. p_40 — 2 eventos
    5. p_50 — 1 eventos
```

### Part 3 — API de Métricas

```bash
python part3_api/api.py
```

Esto muestra las métricas con diferentes filtros y opcionalmente inicia el
servidor HTTP en `http://127.0.0.1:8080`.

**Probar el servidor HTTP:**

```bash
# Sin filtros
curl "http://127.0.0.1:8080/metrics"

# Filtrar por país
curl "http://127.0.0.1:8080/metrics?country=CR"

# Filtrar por rango de fechas
curl "http://127.0.0.1:8080/metrics?from_date=2026-04-30T00:00:00Z&to_date=2026-05-03T23:59:59Z"

# Combinar filtros
curl "http://127.0.0.1:8080/metrics?country=MX&from_date=2026-04-29T00:00:00Z"
```

### Part 4 — Diseño en Tinybird

El documento de diseño se encuentra en [`part4_design/DESIGN.md`](part4_design/DESIGN.md).
No requiere ejecución; es un documento técnico que cubre:

- Modelado del Data Source (schema, engine, sorting key)
- SQL de 4 Pipes (revenue, conversion, top products, funnel)
- Estrategia de deduplicación
- Plan de escalamiento

## Dataset de Prueba

El archivo `data/sample_events.json` contiene **24 eventos** diseñados para
cubrir todos los casos de validación:

| Caso                          | Eventos                              |
|-------------------------------|--------------------------------------|
| Eventos válidos               | evt_001 a evt_016, evt_022           |
| Duplicados                    | evt_003 (×2), evt_007 (×2)           |
| Purchase sin price            | evt_017 (price = 0)                  |
| event_type inválido           | evt_018 (tipo: "invalid_event")      |
| event_id vacío                | Evento sin ID (posición 21)          |
| user_id vacío                 | evt_020 (user_id: "")                |
| timestamp inválido            | evt_021 (timestamp: "not-a-date")    |
| Países                        | CR, MX, US                           |
| Rango de fechas               | 2026-04-28 a 2026-05-04 (~1 semana)  |
| Purchases válidos con price>0 | evt_003, evt_007, evt_011            |

## Decisiones de Diseño

### Arquitectura general

- **Separación por módulos:** cada parte del challenge tiene su propio módulo
  Python, manteniendo responsabilidades claras y permitiendo importaciones
  cruzadas solo donde es necesario (metrics importa validator, api importa ambos).

- **Sin dependencias externas:** todo el proyecto usa exclusivamente la
  biblioteca estándar de Python. Esto demuestra dominio del lenguaje y
  reduce complejidad de deployment.

### Validación (Part 1)

- **`_errors` como metadato:** los eventos inválidos se enriquecen con la
  clave `_errors` para facilitar debugging. Esta clave nunca conflicta con
  campos de evento ya que usa el prefijo `_`.

- **Deduplicación en validación:** los duplicados se detectan por `event_id`.
  Solo la primera aparición se mantiene en `valid_events`; las siguientes se
  mueven a `invalid_events` con el error "Evento duplicado".

- **Parseo de timestamps:** se usa `datetime.fromisoformat()` con manejo del
  sufijo `Z` (→ `+00:00`) para compatibilidad con Python 3.10.

### Métricas (Part 2)

- **Conversion rate:** se define como `compradores / viewers` (usuarios que
  hicieron al menos un `purchase` / usuarios que hicieron al menos un
  `product_view`). Se decidió usar `product_view` como denominador porque
  representa la entrada del funnel de compra.

- **Top products:** cuenta interacciones de **cualquier tipo** de evento,
  no solo views, lo cual da una visión más completa de la popularidad
  del producto.

### API (Part 3)

- **Función pura + servidor:** `get_metrics()` es una función pura que
  puede usarse programáticamente sin levantar el servidor. El servidor
  HTTP es una capa adicional que envuelve esta función.

- **Reutilización de componentes:** la API reutiliza `EventValidator` y
  `MetricsCalculator` directamente, evitando duplicación de lógica.

- **Filtros inclusivos:** tanto `from_date` como `to_date` son **inclusivos**
  para evitar gaps en los datos.

### Diseño Tinybird (Part 4)

- **`ReplacingMergeTree`** sobre `AggregatingMergeTree` como engine principal
  porque se necesitan consultas sobre eventos individuales, no solo agregados.

- **Deduplicación en tres capas:** almacenamiento (engine), consulta (FINAL),
  y upstream (validación previa). Esto proporciona defensa en profundidad.

- **Materialización selectiva:** solo se sugieren Materialized Views para
  métricas con alto volumen de consultas, no para todas las queries.
