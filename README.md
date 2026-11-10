# MiniProyecto3_LuisChali — MVP de hiperpersonalización para NovaBank

Prototipo funcional (MVP) para el curso **131 - Programación para la Ciencia de Datos** (UMG, Sección A).

**Servicio implementado:** predicción de **riesgo de abandono (churn)** de clientes con una **acción de retención personalizada** para cada cliente.

## Flujo del prototipo

```
[Datos sintéticos] -> [Ingesta] -> [SQLite: Bronze -> Silver -> Gold] -> [Modelo]
   -> [Predicción + acción] -> [API FastAPI] -> [Robot UiPath] -> [Power BI]
```

## Stack (todo gratuito)

| Capa | Herramienta |
|---|---|
| Datos sintéticos | Python, pandas, numpy, Faker |
| Almacenamiento | SQLite (capas Bronze / Silver / Gold) |
| Modelo | scikit-learn |
| API | FastAPI + uvicorn |
| Pruebas | pytest + pytest-html |
| Automatización | UiPath Community (Studio + Orchestrator) |
| Visualización | Power BI Desktop |
| Versionado | Git + GitHub |

## Estructura del repositorio

```
src/            código del pipeline (generación, ingesta, transformación, modelo, API)
tests/          pruebas de ingesta y pruebas unitarias (pytest)
data/raw/       CSV generados por el script de datos sintéticos
data/db/        base de datos SQLite (novabank.db)
uipath/         proyecto de automatización en UiPath
powerbi/        tablero de Power BI (.pbix)
docs/           diagramas (fuentes draw.io) y capturas
reports/        reportes de pruebas y métricas del modelo
```

## Instalación

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / Mac
source .venv/bin/activate

pip install -r requirements.txt
```

## Ejecución

Todos los comandos se corren desde la carpeta raíz del repositorio.

### Pipeline completo (un solo comando)

```bash
python run_pipeline.py              # usa los CSV existentes en data/raw/
python run_pipeline.py --regenerar  # vuelve a generar los datos sintéticos
```

Crea la base `data/db/novabank.db` con todas las capas. También se puede correr cada paso por separado:

### Parte 1 — Datos sintéticos y validación

```bash
python -m src.generar_datos    # crea data/raw/clientes.csv, transacciones.csv, interacciones.csv
python -m src.validar_datos    # revisa rangos, nulos, duplicados y distribuciones
```

- Se generan **1,500 clientes**, ~48 mil transacciones (12 meses) y ~3 mil interacciones con servicio al cliente.
- La semilla fija (`SEMILLA = 42` en `src/config.py`) hace que los datos sean siempre los mismos.
- Se simulan errores típicos de los sistemas fuente (~1 % de nulos y ~0.5 % de transacciones duplicadas)
  para que la capa Silver tenga algo que limpiar.
- El reporte queda en `reports/validacion_datos.md` y las gráficas en `reports/figuras/`.

### Parte 2 — Almacenamiento en SQLite (Bronze → Silver → Gold)

```bash
python -m src.ingesta       # CSV -> Bronze
python -m src.transformar   # Bronze -> Silver -> Gold
```

| Capa | Tablas | Qué contiene |
|---|---|---|
| **Bronze** | `bronze_clientes`, `bronze_transacciones`, `bronze_interacciones` | Copia fiel de los CSV, todo como texto, más `_archivo_origen` y `_fecha_carga` |
| **Silver** | `silver_clientes`, `silver_transacciones`, `silver_interacciones` | Tipos correctos, sin duplicados, nulos imputados (ingreso → mediana del segmento; canal → moda o "Desconocido") |
| **Gold** | `gold_features_cliente` | 1 fila por cliente: perfil + actividad 12 meses + tendencia últimos 3 meses + quejas + `abandono` |
| Control | `control_cargas` | Bitácora de cada carga: capa, tabla, registros de entrada y salida, detalle |

Variables de comportamiento calculadas en Gold:

| Variable | Descripción |
|---|---|
| `trx_12m`, `monto_12m` | Número y monto total de transacciones en 12 meses |
| `trx_ult_3m` | Transacciones en los últimos 3 meses |
| `tendencia_actividad` | Promedio mensual últimos 3 meses ÷ promedio mensual 9 meses anteriores (< 1 = baja actividad) |
| `dias_sin_trx` | Días desde la última transacción hasta la fecha de corte |
| `pct_digital` | % de transacciones por App o Web |
| `tipos_distintos` | Cuántos tipos de transacción usa el cliente |
| `consultas_12m`, `quejas_12m`, `quejas_no_resueltas` | Interacciones con servicio al cliente |

### Parte 3 — Pruebas de ingesta (pytest)

```bash
pytest -m ingesta
```

Al terminar se genera automáticamente el reporte `reports/pruebas_ingesta.html`
(HTML simple, sin JavaScript, se abre en cualquier navegador).

33 pruebas que comprueban que los datos llegan **completos y correctos** a cada capa:

| Capa | Qué se comprueba |
|---|---|
| Bronze | Mismo número de registros y columnas que el CSV; metadatos de carga completos |
| Silver | Mínimo 1,000 clientes; no se pierden registros válidos; columnas y tipos esperados; sin nulos; sin duplicados; integridad referencial; rangos válidos |
| Gold | Una fila por cliente; columnas del modelo; sin nulos; el total de transacciones cuadra con Silver; tasa de abandono realista; una predicción válida por cliente |
| Control | La bitácora registra todas las tablas de las 3 capas |

> Si la base no existe, las pruebas la construyen automáticamente antes de correr.

### Parte 4 — Modelo, métrica y predicciones

```bash
python -m src.modelo     # entrena, compara y evalúa
python -m src.predecir   # predice cada cliente y guarda en Gold
```

**Qué predice:** la probabilidad de que el cliente **abandone el banco en los próximos 90 días**.

| | Regresión Logística (elegido) | Random Forest |
|---|---|---|
| AUC validación cruzada (5 pliegues) | **0.843** ± 0.048 | 0.821 ± 0.047 |
| AUC conjunto de prueba (375 clientes) | **0.822** | 0.820 |

Métricas del modelo elegido en el conjunto de prueba (umbral 0.30, elegido por máximo F1 en validación cruzada):
**AUC 0.822 · F1 0.556 · Precisión 0.506 · Recall 0.618 · Exactitud 0.821**.

- Las probabilidades están **calibradas** (no se usa `class_weight`): en el grupo de riesgo Alto la probabilidad
  media es 66 % y el abandono real 70 %.
- Variables más importantes: transacciones de los últimos 3 meses, transacciones del año, quejas no resueltas,
  días sin transacciones y número de productos.
- Métricas completas: `reports/metricas_modelo.json` · Gráficas: `reports/figuras/03_curva_roc.png`,
  `04_matriz_confusion.png`, `05_importancia_variables.png`.

**Nivel de riesgo y acción recomendada** (`src/predecir.py` → tabla `gold_predicciones`):

| Riesgo | Probabilidad | Acciones posibles (según el perfil del cliente) |
|---|---|---|
| Alto | ≥ 45 % | Resolver queja pendiente · Llamada de asesor personal (alto valor) · Campaña de reactivación · Exoneración de comisiones |
| Medio | 20 % – 45 % | Tarjeta de crédito preaprobada (venta cruzada) · Invitación a la app · Plan de ahorro programado |
| Bajo | < 20 % | Sin acción: seguimiento normal |

> Las siguientes partes del pipeline se agregan a medida que avanza el proyecto.
