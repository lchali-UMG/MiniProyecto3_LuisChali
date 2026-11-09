"""Configuración central del proyecto: rutas y parámetros."""
from pathlib import Path

# Rutas
RAIZ = Path(__file__).resolve().parents[1]
DATA_RAW = RAIZ / "data" / "raw"
DB_PATH = RAIZ / "data" / "db" / "novabank.db"
MODELS_DIR = RAIZ / "models"
REPORTS_DIR = RAIZ / "reports"
FIGURAS_DIR = REPORTS_DIR / "figuras"

# Parámetros de los datos sintéticos
SEMILLA = 42                    # para que los datos sean siempre los mismos
N_CLIENTES = 1500
FECHA_INICIO = "2025-11-01"     # inicio de la ventana de 12 meses observada
FECHA_CORTE = "2026-10-31"      # fecha de corte (hoy para el modelo)
TASA_ABANDONO_OBJETIVO = 0.18   # ~18 % de clientes abandonan

# Inicio de la ventana "reciente" (últimos 3 meses antes del corte)
FECHA_INICIO_RECIENTE = "2026-08-01"

# Archivos fuente que se ingieren a Bronze
FUENTES = {
    "clientes": "clientes.csv",
    "transacciones": "transacciones.csv",
    "interacciones": "interacciones.csv",
}

# Simular errores típicos de los sistemas fuente (nulos y duplicados)
# para que la capa Silver tenga algo que limpiar.
INYECTAR_ERRORES = True
