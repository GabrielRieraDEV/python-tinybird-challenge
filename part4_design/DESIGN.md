# Diseño de Solución en Tinybird — E-commerce Real-Time Analytics

## 1. Modelado del Data Source

### Definición del esquema

El Data Source en Tinybird almacena los eventos de e-commerce crudos. La tabla
subyacente usa ClickHouse como motor, por lo que elegimos **`ReplacingMergeTree`**
para manejar duplicados de forma nativa.

```sql
SCHEMA >
    event_id    String,
    user_id     String,
    event_type  LowCardinality(String),
    product_id  String,
    timestamp   DateTime64(3, 'UTC'),
    price       Float64,
    country     LowCardinality(String)

ENGINE "ReplacingMergeTree"
ENGINE_SORTING_KEY "event_id, timestamp"
ENGINE_PARTITION_KEY "toYYYYMM(timestamp)"
```

### Decisiones de diseño

| Columna      | Tipo                     | Justificación                                                                                 |
|--------------|--------------------------|-----------------------------------------------------------------------------------------------|
| `event_id`   | `String`                 | Identificador único del evento. Forma parte de la sorting key para deduplicación.             |
| `event_type` | `LowCardinality(String)` | Solo 3 valores posibles; `LowCardinality` reduce almacenamiento y acelera filtros.            |
| `country`    | `LowCardinality(String)` | Conjunto finito de países; misma optimización.                                                |
| `timestamp`  | `DateTime64(3, 'UTC')`   | Precisión de milisegundos; timezone UTC para consistencia.                                    |
| `price`      | `Float64`                | Permite manejar decimales en precios. Podría usarse `Decimal64(2)` para mayor precisión.      |

- **Engine:** `ReplacingMergeTree` permite que ClickHouse elimine filas duplicadas
  durante los merges de background basándose en la sorting key.
- **Sorting Key:** `(event_id, timestamp)` — ordena por ID de evento y luego por
  timestamp. Esto optimiza consultas de deduplicación y búsquedas por evento.
- **Partition Key:** `toYYYYMM(timestamp)` — particiona por mes, lo cual facilita
  la gestión de datos históricos (TTL, drops) y mejora el rendimiento al hacer
  pruning de particiones en consultas con filtros de fecha.

---

## 2. Pipes (Endpoints de Consulta)

### 2.1. `pipe_revenue` — Ingresos totales y por país

Calcula los ingresos totales y desglosados por país, considerando solo eventos
de tipo `purchase`.

```sql
%
-- pipe_revenue.pipe
-- Parámetro opcional: country (String)

SELECT
    country,
    count()                 AS total_purchases,
    round(sum(price), 2)    AS total_revenue,
    round(avg(price), 2)    AS avg_ticket
FROM ecommerce_events FINAL
WHERE event_type = 'purchase'
  AND price > 0
  {% if defined(country) %}
  AND country = {{ String(country) }}
  {% end %}
GROUP BY country
ORDER BY total_revenue DESC
```

**Notas:**
- Se usa `FINAL` para garantizar que no se cuenten duplicados.
- El parámetro `country` es opcional; si se omite retorna todos los países.
- Se incluye ticket promedio como métrica complementaria.

---

### 2.2. `pipe_conversion` — Tasa de conversión

Calcula la tasa de conversión como la proporción de usuarios que realizaron
al menos un `purchase` sobre los que realizaron al menos un `product_view`.

```sql
%
-- pipe_conversion.pipe

SELECT
    viewers.country                                     AS country,
    viewers.total_viewers,
    COALESCE(buyers.total_buyers, 0)                    AS total_buyers,
    round(COALESCE(buyers.total_buyers, 0) / viewers.total_viewers, 4) AS conversion_rate
FROM (
    SELECT
        country,
        uniqExact(user_id) AS total_viewers
    FROM ecommerce_events FINAL
    WHERE event_type = 'product_view'
    GROUP BY country
) AS viewers
LEFT JOIN (
    SELECT
        country,
        uniqExact(user_id) AS total_buyers
    FROM ecommerce_events FINAL
    WHERE event_type = 'purchase'
      AND price > 0
    GROUP BY country
) AS buyers ON viewers.country = buyers.country
ORDER BY conversion_rate DESC
```

**Notas:**
- `uniqExact` cuenta usuarios únicos de forma exacta.
- Se usa `LEFT JOIN` para incluir países donde hay vistas pero no compras.
- La conversión se calcula por país; puede adaptarse fácilmente para un total global.

---

### 2.3. `pipe_top_products` — Productos más vistos/comprados

Retorna los productos con mayor frecuencia de interacción, segmentando
por tipo de evento.

```sql
%
-- pipe_top_products.pipe
-- Parámetro opcional: event_type (String), limit (Int32, default 10)

SELECT
    product_id,
    event_type,
    count() AS total_events,
    uniqExact(user_id) AS unique_users
FROM ecommerce_events FINAL
{% if defined(event_type) %}
WHERE event_type = {{ String(event_type) }}
{% end %}
GROUP BY product_id, event_type
ORDER BY total_events DESC
LIMIT {{ Int32(limit, 10) }}
```

**Notas:**
- Permite filtrar por `event_type` específico (e.g. solo `product_view`).
- Incluye conteo de usuarios únicos por producto para análisis de alcance.
- Límite configurable con valor por defecto de 10.

---

### 2.4. `pipe_funnel` — Funnel product_view → add_to_cart → purchase

Análisis de embudo de conversión que muestra cuántos usuarios pasan
de cada etapa a la siguiente.

```sql
%
-- pipe_funnel.pipe
-- Parámetro opcional: country (String)

WITH
    viewers AS (
        SELECT uniqExact(user_id) AS cnt
        FROM ecommerce_events FINAL
        WHERE event_type = 'product_view'
        {% if defined(country) %}
        AND country = {{ String(country) }}
        {% end %}
    ),
    carters AS (
        SELECT uniqExact(user_id) AS cnt
        FROM ecommerce_events FINAL
        WHERE event_type = 'add_to_cart'
        {% if defined(country) %}
        AND country = {{ String(country) }}
        {% end %}
    ),
    buyers AS (
        SELECT uniqExact(user_id) AS cnt
        FROM ecommerce_events FINAL
        WHERE event_type = 'purchase'
          AND price > 0
        {% if defined(country) %}
        AND country = {{ String(country) }}
        {% end %}
    )
SELECT
    viewers.cnt                                             AS step_1_views,
    carters.cnt                                             AS step_2_cart,
    buyers.cnt                                              AS step_3_purchase,
    round(carters.cnt / viewers.cnt, 4)                     AS view_to_cart_rate,
    round(buyers.cnt / carters.cnt, 4)                      AS cart_to_purchase_rate,
    round(buyers.cnt / viewers.cnt, 4)                      AS overall_conversion
FROM viewers, carters, buyers
```

**Notas:**
- Cada paso del funnel es independiente (no se requiere que sea el mismo
  usuario secuencialmente — es un funnel "abierto").
- Para un funnel secuencial estricto (mismo usuario pasa por cada etapa),
  se usarían JOINs o `windowFunnel()` de ClickHouse.
- Filtrable opcionalmente por país.

---

## 3. Estrategia de Deduplicación

La deduplicación es un problema crítico en sistemas de eventos en tiempo real
donde los productores pueden reintentar envíos. Se aborda en múltiples capas:

### 3.1. Capa de almacenamiento — `ReplacingMergeTree`

```
ENGINE "ReplacingMergeTree"
ENGINE_SORTING_KEY "event_id, timestamp"
```

- `ReplacingMergeTree` mantiene la **última versión** de cada fila con
  la misma sorting key durante los merges de background.
- **Limitación:** los merges no son inmediatos. Entre un merge y otro,
  pueden existir filas duplicadas temporalmente.
- **Solución en consultas:** usar `FINAL` en las queries para forzar
  deduplicación al momento de la lectura.

### 3.2. Capa de consulta — `FINAL` y `argMax`

```sql
-- Opción A: Usar FINAL (recomendado para tablas moderadas)
SELECT * FROM ecommerce_events FINAL WHERE ...

-- Opción B: Usar argMax para tablas muy grandes
SELECT
    event_id,
    argMax(user_id, timestamp)    AS user_id,
    argMax(event_type, timestamp) AS event_type,
    argMax(product_id, timestamp) AS product_id,
    max(timestamp)                AS timestamp,
    argMax(price, timestamp)      AS price,
    argMax(country, timestamp)    AS country
FROM ecommerce_events
GROUP BY event_id
```

| Estrategia | Ventajas                         | Desventajas                                |
|------------|----------------------------------|--------------------------------------------|
| `FINAL`    | Simple, correcto                 | Puede ser lento en tablas muy grandes       |
| `argMax`   | Mejor rendimiento en tablas grandes | Query más compleja                       |

### 3.3. Capa upstream — Validación antes de ingestar

- **Idempotencia:** el productor de eventos asigna un `event_id` único y
  determinístico (e.g. hash de `user_id + product_id + timestamp + action`).
- **Buffer de deduplicación:** mantener un caché (Redis, Bloom filter) de
  los últimos N event_ids procesados para rechazar duplicados antes de enviar
  a Tinybird.
- **Ventana temporal:** Tinybird soporta deduplicación nativa en la ingesta
  dentro de una ventana temporal configurable.

### 3.4. Alternativa: `AggregatingMergeTree`

Para métricas pre-agregadas donde no se necesitan los eventos individuales:

```sql
-- Materialized View con AggregatingMergeTree
ENGINE "AggregatingMergeTree"
ENGINE_SORTING_KEY "country, toDate(timestamp)"

SELECT
    country,
    toDate(timestamp)              AS event_date,
    countState()                   AS total_events,
    uniqState(user_id)             AS unique_users,
    sumStateIf(price, event_type = 'purchase') AS total_revenue
FROM ecommerce_events
GROUP BY country, event_date
```

Esto pre-calcula agregaciones incrementalmente, eliminando duplicados por diseño
ya que las funciones `-State/-Merge` son idempotentes para la misma clave.

---

## 4. Estrategia de Escalamiento

### 4.1. Ingesta de datos

**Para volumen moderado (< 10K eventos/segundo):**
- Usar la **Events API** de Tinybird (HTTP POST con NDJSON).
- Batching de eventos cada 1–5 segundos para reducir llamadas HTTP.

```bash
curl -X POST "https://api.tinybird.co/v0/events?name=ecommerce_events" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"event_id":"evt_001","user_id":"u_123",...}'
```

**Para alto volumen (> 10K eventos/segundo):**
- Usar el **Kafka Connector** de Tinybird para consumir directamente desde
  un topic de Kafka.
- Configurar un consumer group dedicado con `auto.offset.reset=earliest`.
- Esto permite backpressure natural y tolerancia a fallos.

### 4.2. Particionado y almacenamiento

```sql
ENGINE_PARTITION_KEY "toYYYYMM(timestamp)"
```

- **Particionado mensual** permite:
  - Eliminar datos antiguos con `ALTER TABLE ... DROP PARTITION`.
  - Aplicar TTL para limpieza automática.
  - Mejorar rendimiento de consultas con filtro de fecha (partition pruning).
- Para volúmenes extremos, considerar particionado diario: `toYYYYMMDD(timestamp)`.

### 4.3. Materialización de métricas

Usar **Materialized Views** para pre-calcular métricas frecuentes:

```
┌──────────────────┐     ┌─────────────────────────┐     ┌──────────────────┐
│ ecommerce_events │────►│ MV: revenue_by_country  │────►│ Pipe endpoint    │
│  (Data Source)   │     │  (AggregatingMergeTree) │     │  (lectura rápida)│
└──────────────────┘     └─────────────────────────┘     └──────────────────┘
```

Beneficios:
- Las queries leen de tablas pre-agregadas, mucho más pequeñas.
- La materialización es incremental: solo procesa datos nuevos.
- Latencia de consulta consistente sin importar el volumen total.

### 4.4. Seguridad y control de acceso

- **Tokens de lectura:** crear tokens con permisos granulares por pipe.
  Cada consumidor (dashboard, app móvil) recibe un token específico.
- **Tokens de escritura:** separar tokens de ingesta de los de lectura.
- **Rate limiting:** configurar límites por token para evitar abuso.
- **Row-level security:** usar filtros de token para restringir datos
  por país o tenant en escenarios multi-tenant.

```
Token: dashboard_cr
  Scopes: READ
  Pipes: pipe_revenue, pipe_conversion, pipe_funnel
  Filter: country = 'CR'
```

### 4.5. Arquitectura completa

```
Productores          │        Tinybird                     │  Consumidores
─────────────────────┼─────────────────────────────────────┼──────────────
                     │                                     │
 App Web ──POST──►   │  Events API ──► ecommerce_events   │
                     │                    │                │
 App Móvil ──POST─►  │                    ├─► MV revenue   │──► Dashboard
                     │                    ├─► MV conversion│──► App Admin
 Kafka ──Connector─► │                    └─► MV funnel    │──► Alertas
                     │                                     │
                     │  Pipes ──► API Endpoints (REST)     │──► Clientes
                     │                                     │
```

### 4.6. Monitoreo y observabilidad

- Usar el **Service Data Sources** de Tinybird para monitorear:
  - Latencia de ingesta
  - Errores de parseo
  - Volumen de datos por hora
  - Tiempos de respuesta de pipes
- Configurar alertas para anomalías en el volumen de eventos.
- Dashboards internos con las métricas operacionales.
