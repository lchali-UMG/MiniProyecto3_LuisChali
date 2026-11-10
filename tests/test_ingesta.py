"""
Parte 3 - Pruebas de ingesta.

Comprueban que los datos llegan COMPLETOS y CORRECTOS a cada capa:
  1. Número de registros
  2. Columnas y tipos
  3. Nulos
  4. Duplicados
  (+ integridad referencial, rangos y bitácora de cargas)

Uso:
  pytest -m ingesta
  pytest -m ingesta --html=reports/pruebas_ingesta.html --self-contained-html
"""
import pytest

pytestmark = pytest.mark.ingesta

TABLAS = ["clientes", "transacciones", "interacciones"]
LLAVES = {"clientes": "cliente_id", "transacciones": "transaccion_id", "interacciones": "interaccion_id"}
COLUMNAS_CONTROL = ["_archivo_origen", "_fecha_carga"]

# Esquema esperado en Silver (nombre de columna -> tipo SQLite)
ESQUEMA_SILVER = {
    "clientes": {
        "cliente_id": "TEXT", "nombre": "TEXT", "genero": "TEXT", "edad": "INTEGER",
        "departamento": "TEXT", "segmento": "TEXT", "ingreso_mensual": "REAL",
        "antiguedad_meses": "INTEGER", "fecha_alta": "TEXT", "num_productos": "INTEGER",
        "tiene_tarjeta_credito": "INTEGER", "tiene_prestamo": "INTEGER",
        "saldo_promedio": "REAL", "score_crediticio": "INTEGER",
        "canal_preferido": "TEXT", "abandono": "INTEGER",
    },
    "transacciones": {
        "transaccion_id": "TEXT", "cliente_id": "TEXT", "fecha": "TEXT",
        "tipo": "TEXT", "canal": "TEXT", "monto": "REAL",
    },
    "interacciones": {
        "interaccion_id": "TEXT", "cliente_id": "TEXT", "fecha": "TEXT",
        "tipo": "TEXT", "canal": "TEXT", "resuelta": "INTEGER",
    },
}

COLUMNAS_GOLD = [
    "cliente_id", "nombre", "genero", "edad", "departamento", "segmento",
    "ingreso_mensual", "antiguedad_meses", "fecha_alta", "num_productos",
    "tiene_tarjeta_credito", "tiene_prestamo", "saldo_promedio", "score_crediticio",
    "canal_preferido", "trx_12m", "monto_12m", "trx_ult_3m", "pct_digital",
    "tipos_distintos", "tendencia_actividad", "dias_sin_trx", "consultas_12m",
    "quejas_12m", "quejas_no_resueltas", "abandono",
]


def esquema(consultar, tabla):
    info = consultar(f"PRAGMA table_info({tabla})")
    return dict(zip(info["name"], info["type"]))


def contar(consultar, tabla):
    return int(consultar(f"SELECT COUNT(*) AS n FROM {tabla}")["n"][0])


# ===========================================================================
# BRONZE: ¿llegó todo lo que venía en el archivo?
# ===========================================================================
@pytest.mark.parametrize("tabla", TABLAS)
def test_bronze_mismo_numero_de_registros_que_el_csv(tabla, consultar, csv_fuente):
    """Bronze tiene exactamente las mismas filas que el CSV de origen."""
    assert contar(consultar, f"bronze_{tabla}") == len(csv_fuente(tabla))


@pytest.mark.parametrize("tabla", TABLAS)
def test_bronze_mismas_columnas_que_el_csv(tabla, consultar, csv_fuente):
    """Bronze conserva todas las columnas del CSV + 2 columnas de control."""
    esperadas = list(csv_fuente(tabla).columns) + COLUMNAS_CONTROL
    assert list(esquema(consultar, f"bronze_{tabla}")) == esperadas


@pytest.mark.parametrize("tabla", TABLAS)
def test_bronze_metadatos_de_carga_completos(tabla, consultar):
    """Cada registro de Bronze sabe de qué archivo vino y cuándo se cargó."""
    nulos = consultar(
        f"SELECT COUNT(*) AS n FROM bronze_{tabla} "
        f"WHERE _archivo_origen IS NULL OR _fecha_carga IS NULL")["n"][0]
    assert nulos == 0


# ===========================================================================
# SILVER: ¿quedó limpio y con los tipos correctos?
# ===========================================================================
def test_silver_clientes_minimo_1000(consultar):
    """El enunciado pide al menos 1,000 clientes."""
    assert contar(consultar, "silver_clientes") >= 1000


@pytest.mark.parametrize("tabla", TABLAS)
def test_silver_no_pierde_registros_validos(tabla, consultar):
    """Silver tiene un registro por cada llave única de Bronze (solo se quitan duplicados)."""
    llave = LLAVES[tabla]
    unicos_bronze = consultar(f"SELECT COUNT(DISTINCT {llave}) AS n FROM bronze_{tabla}")["n"][0]
    assert contar(consultar, f"silver_{tabla}") == unicos_bronze


@pytest.mark.parametrize("tabla", TABLAS)
def test_silver_columnas_y_tipos(tabla, consultar):
    """Silver tiene las columnas esperadas, cada una con su tipo de dato."""
    assert esquema(consultar, f"silver_{tabla}") == ESQUEMA_SILVER[tabla]


@pytest.mark.parametrize("tabla", TABLAS)
def test_silver_sin_nulos(tabla, consultar):
    """Ninguna columna de Silver tiene valores nulos."""
    df = consultar(f"SELECT * FROM silver_{tabla}")
    nulos = df.isna().sum()
    assert nulos.sum() == 0, f"Columnas con nulos: {nulos[nulos > 0].to_dict()}"


@pytest.mark.parametrize("tabla", TABLAS)
def test_silver_sin_duplicados(tabla, consultar):
    """La llave de cada tabla de Silver es única."""
    llave = LLAVES[tabla]
    dup = consultar(
        f"SELECT COUNT(*) AS n FROM (SELECT {llave} FROM silver_{tabla} "
        f"GROUP BY {llave} HAVING COUNT(*) > 1)")["n"][0]
    assert dup == 0


@pytest.mark.parametrize("tabla", ["transacciones", "interacciones"])
def test_silver_integridad_referencial(tabla, consultar):
    """Toda transacción e interacción pertenece a un cliente existente."""
    huerfanos = consultar(
        f"SELECT COUNT(*) AS n FROM silver_{tabla} t "
        f"LEFT JOIN silver_clientes c ON t.cliente_id = c.cliente_id "
        f"WHERE c.cliente_id IS NULL")["n"][0]
    assert huerfanos == 0


def test_silver_rangos_validos(consultar):
    """Los valores clave están dentro de rangos realistas."""
    c = consultar("SELECT edad, ingreso_mensual, score_crediticio, abandono FROM silver_clientes")
    assert c["edad"].between(18, 80).all()
    assert (c["ingreso_mensual"] > 0).all()
    assert c["score_crediticio"].between(300, 850).all()
    assert set(c["abandono"].unique()) <= {0, 1}
    t = consultar("SELECT MIN(monto) AS minimo FROM silver_transacciones")
    assert t["minimo"][0] > 0


# ===========================================================================
# GOLD: ¿está listo para el modelo?
# ===========================================================================
def test_gold_un_registro_por_cliente(consultar):
    """Gold tiene exactamente una fila por cliente de Silver."""
    n_gold = contar(consultar, "gold_features_cliente")
    unicos = consultar("SELECT COUNT(DISTINCT cliente_id) AS n FROM gold_features_cliente")["n"][0]
    assert n_gold == contar(consultar, "silver_clientes") == unicos


def test_gold_columnas_esperadas(consultar):
    """Gold tiene todas las variables que usa el modelo."""
    assert list(esquema(consultar, "gold_features_cliente")) == COLUMNAS_GOLD


def test_gold_sin_nulos(consultar):
    """El modelo no acepta nulos: Gold debe estar completo."""
    df = consultar("SELECT * FROM gold_features_cliente")
    assert df.isna().sum().sum() == 0


def test_gold_cuadra_con_silver(consultar):
    """La suma de transacciones por cliente en Gold = total de transacciones en Silver."""
    total_gold = consultar("SELECT SUM(trx_12m) AS n FROM gold_features_cliente")["n"][0]
    assert total_gold == contar(consultar, "silver_transacciones")


def test_gold_tasa_de_abandono_razonable(consultar):
    """La tasa de abandono está en un rango realista para banca (5 % a 40 %)."""
    tasa = consultar("SELECT AVG(abandono) AS t FROM gold_features_cliente")["t"][0]
    assert 0.05 <= tasa <= 0.40


# ===========================================================================
# Bitácora de cargas
# ===========================================================================
def test_control_cargas_registra_todas_las_capas(consultar):
    """La bitácora tiene registro de cada tabla cargada en Bronze, Silver y Gold."""
    tablas = set(consultar("SELECT DISTINCT tabla FROM control_cargas")["tabla"])
    esperadas = {f"{capa}_{t}" for capa in ["bronze", "silver"] for t in TABLAS}
    esperadas.add("gold_features_cliente")
    assert esperadas <= tablas
