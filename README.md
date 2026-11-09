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

> Las siguientes partes del pipeline se agregan a medida que avanza el proyecto.
