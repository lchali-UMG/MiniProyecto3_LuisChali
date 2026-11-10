"""Configuración compartida de las pruebas."""
import pandas as pd
import pytest

from src import config, ingesta, transformar
from src.db import conectar


def pytest_html_report_title(report):
    """Título del reporte HTML (pytest-html)."""
    report.title = "Reporte de pruebas - MVP NovaBank (riesgo de abandono)"


@pytest.fixture(scope="session")
def con():
    """Conexión a la base del pipeline. Si todavía no existe, la construye."""
    if not config.DB_PATH.exists():
        ingesta.main()
        transformar.main()
    conexion = conectar()
    yield conexion
    conexion.close()


@pytest.fixture(scope="session")
def consultar(con):
    """Atajo para ejecutar un SELECT y obtener un DataFrame."""
    def _consultar(sql):
        return pd.read_sql_query(sql, con)
    return _consultar


@pytest.fixture(scope="session")
def csv_fuente():
    """Lee un CSV fuente tal como está en data/raw/."""
    def _leer(nombre):
        return pd.read_csv(config.DATA_RAW / config.FUENTES[nombre], dtype=str)
    return _leer
