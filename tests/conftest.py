"""Configuración compartida de las pruebas."""
import time

import pandas as pd
import pytest

from src import config, ingesta, modelo, predecir, transformar
from src.db import conectar
from tests.reporte_html import escribir_reporte, resultado_desde_reporte


# ---------------------------------------------------------------------------
# Reporte HTML propio (se escribe en reports/ al terminar las pruebas)
# ---------------------------------------------------------------------------
_RESULTADOS = {}
_INICIO = {}


def pytest_sessionstart(session):
    _INICIO["t"] = time.time()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    salida = yield
    rep = salida.get_result()
    # Se guarda el resultado de la prueba (o el error si falló la preparación)
    if rep.when == "call" or (rep.when == "setup" and not rep.passed):
        _RESULTADOS[item.nodeid] = resultado_desde_reporte(item, rep)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if _RESULTADOS:
        ruta = escribir_reporte(list(_RESULTADOS.values()), config.option.markexpr,
                                time.time() - _INICIO.get("t", time.time()))
        terminalreporter.write_line(f"Reporte HTML: {ruta}")


@pytest.fixture(scope="session")
def con():
    """Conexión a la base del pipeline. Si todavía no existe, la construye."""
    if not config.DB_PATH.exists():
        ingesta.main()
        transformar.main()
        modelo.main()
        predecir.main()
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
