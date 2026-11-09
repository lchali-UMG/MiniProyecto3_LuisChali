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

> Las siguientes partes del pipeline se agregan a medida que avanza el proyecto.
