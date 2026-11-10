"""
Parte 6 - Pruebas unitarias.

Prueban funciones sueltas con datos pequeños hechos a mano (no dependen de
la base real del pipeline):
  - Regla de decisión: nivel de riesgo y acción recomendada
  - Limpieza de la capa Silver
  - Cálculo de variables de la capa Gold
  - Métricas del modelo
  - API: respuestas 200, 201, 404 y 422 (con una base temporal)

Uso:  pytest -m unitaria
"""
import sqlite3

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import api
from src.modelo import calcular_metricas
from src.predecir import nivel_riesgo, recomendar_accion
from src.transformar import construir_features, limpiar_clientes, limpiar_transacciones

pytestmark = pytest.mark.unitaria


# ===========================================================================
# Regla de decisión
# ===========================================================================
@pytest.mark.parametrize("prob, esperado", [
    (0.95, "Alto"), (0.45, "Alto"),      # 0.45 es el límite: ya es Alto
    (0.4499, "Medio"), (0.20, "Medio"),  # 0.20 es el límite: ya es Medio
    (0.1999, "Bajo"), (0.0, "Bajo"),
])
def test_nivel_riesgo_respeta_los_umbrales(prob, esperado):
    """La probabilidad se clasifica en Alto (>= 0.45), Medio (>= 0.20) o Bajo."""
    assert nivel_riesgo(prob) == esperado


def cliente_base(**cambios):
    """Cliente de ejemplo 'neutro'; cada prueba cambia solo lo que necesita."""
    cliente = {
        "nivel_riesgo": "Bajo", "quejas_no_resueltas": 0, "segmento": "Masivo",
        "saldo_promedio": 5000.0, "tendencia_actividad": 1.0, "dias_sin_trx": 5,
        "num_productos": 2, "tiene_tarjeta_credito": 1, "pct_digital": 0.6,
    }
    cliente.update(cambios)
    return cliente


@pytest.mark.parametrize("cambios, accion_esperada", [
    ({"nivel_riesgo": "Alto", "quejas_no_resueltas": 2}, "Resolver queja pendiente"),
    ({"nivel_riesgo": "Alto", "segmento": "Premium"}, "Llamada de asesor personal"),
    ({"nivel_riesgo": "Alto", "tendencia_actividad": 0.2}, "Campaña de reactivación"),
    ({"nivel_riesgo": "Alto"}, "Oferta de retención"),
    ({"nivel_riesgo": "Medio", "num_productos": 1, "tiene_tarjeta_credito": 0}, "Ofrecer tarjeta de crédito"),
    ({"nivel_riesgo": "Medio", "pct_digital": 0.1}, "Invitar a usar la app"),
    ({"nivel_riesgo": "Medio"}, "Sugerir plan de ahorro"),
    ({"nivel_riesgo": "Bajo"}, "Sin acción"),
], ids=["alto-queja", "alto-valor", "alto-inactivo", "alto-general",
        "medio-un-producto", "medio-poco-digital", "medio-general", "bajo"])
def test_recomendar_accion_segun_perfil(cambios, accion_esperada):
    """Cada combinación de riesgo y perfil recibe la acción que dice la regla de negocio."""
    resultado = recomendar_accion(cliente_base(**cambios))
    assert resultado["accion"].startswith(accion_esperada)


def test_recomendar_accion_prioriza_quejas_sobre_valor():
    """Si un cliente Premium de alto riesgo tiene quejas, primero se resuelve la queja."""
    resultado = recomendar_accion(cliente_base(nivel_riesgo="Alto", segmento="Premium", quejas_no_resueltas=1))
    assert resultado["accion"].startswith("Resolver queja")
    assert resultado["prioridad"] == 1


def test_recomendar_accion_devuelve_todos_los_campos():
    """La acción siempre trae acción, canal, motivo y una prioridad entre 1 y 3."""
    for nivel in ["Alto", "Medio", "Bajo"]:
        r = recomendar_accion(cliente_base(nivel_riesgo=nivel))
        assert set(r) == {"accion", "canal_contacto", "motivo", "prioridad"}
        assert r["prioridad"] in (1, 2, 3)


# ===========================================================================
# Limpieza (Silver)
# ===========================================================================
def clientes_crudos():
    """Mini tabla Bronze (todo texto) con un nulo de ingreso, un nulo de canal y un duplicado."""
    return pd.DataFrame({
        "cliente_id": ["C1", "C2", "C3", "C3", "C4"],
        "nombre": ["Ana", "Luis", "Rosa", "Rosa", "José"],
        "genero": ["F", "M", "F", "F", "M"],
        "edad": ["30", "45", "50", "50", "28"],
        "departamento": ["Guatemala"] * 5,
        "segmento": ["Masivo", "Masivo", "Masivo", "Masivo", "Premium"],
        "ingreso_mensual": ["5000", None, "7000", "7000", "30000"],
        "antiguedad_meses": ["10", "20", "30", "30", "40"],
        "fecha_alta": ["2025-12-31"] * 5,
        "num_productos": ["1", "2", "3", "3", "4"],
        "tiene_tarjeta_credito": ["0", "1", "1", "1", "1"],
        "tiene_prestamo": ["0", "0", "1", "1", "0"],
        "saldo_promedio": ["1000.5", "2000", "3000", "3000", "50000"],
        "score_crediticio": ["600", "650", "700", "700", "800"],
        "canal_preferido": ["App", "App", None, None, "Web"],
        "abandono": ["0", "1", "0", "0", "0"],
    })


def test_limpiar_clientes_elimina_duplicados_e_imputa_nulos():
    """Silver quita el cliente repetido e imputa ingreso (mediana del segmento) y canal (moda)."""
    limpio, detalle = limpiar_clientes(clientes_crudos())
    assert len(limpio) == 4
    assert limpio["cliente_id"].is_unique
    assert limpio.isna().sum().sum() == 0
    # Mediana del ingreso del segmento Masivo (5000 y 7000) = 6000
    assert limpio.loc[limpio["cliente_id"] == "C2", "ingreso_mensual"].item() == 6000
    # El canal más común es App
    assert limpio.loc[limpio["cliente_id"] == "C3", "canal_preferido"].item() == "App"
    assert "duplicados eliminados: 1" in detalle


def test_limpiar_clientes_convierte_tipos():
    """Los números que venían como texto quedan como números."""
    limpio, _ = limpiar_clientes(clientes_crudos())
    assert limpio["edad"].dtype == "int64"
    assert limpio["abandono"].dtype == "int64"
    assert limpio["saldo_promedio"].dtype == "float64"


def test_limpiar_transacciones_quita_duplicados_huerfanos_y_montos_invalidos():
    """Se eliminan duplicados, transacciones sin cliente y montos <= 0; el canal nulo queda 'Desconocido'."""
    crudas = pd.DataFrame({
        "transaccion_id": ["T1", "T1", "T2", "T3", "T4"],
        "cliente_id": ["C1", "C1", "C1", "C99", "C2"],
        "fecha": ["2026-01-05 10:00:00"] * 5,
        "tipo": ["Retiro"] * 5,
        "canal": ["ATM", "ATM", None, "App", "App"],
        "monto": ["100", "100", "250", "80", "-5"],
    })
    limpias, _ = limpiar_transacciones(crudas, ids_clientes={"C1", "C2"})
    assert limpias["transaccion_id"].tolist() == ["T1", "T2"]
    assert limpias.loc[limpias["transaccion_id"] == "T2", "canal"].item() == "Desconocido"


# ===========================================================================
# Variables Gold
# ===========================================================================
def test_construir_features_calcula_tendencia_y_quejas():
    """La tendencia compara los últimos 3 meses con los 9 anteriores y se cuentan las quejas."""
    clientes, _ = limpiar_clientes(clientes_crudos())
    # C1: 9 transacciones antes de agosto (1 por mes) y 1 en los últimos 3 meses
    fechas = [f"2025-{m:02d}-15 10:00:00" for m in (11, 12)] + \
             [f"2026-{m:02d}-15 10:00:00" for m in range(1, 8)] + ["2026-09-15 10:00:00"]
    trx = pd.DataFrame({
        "transaccion_id": [f"T{i}" for i in range(10)], "cliente_id": ["C1"] * 10,
        "fecha": fechas, "tipo": ["Retiro"] * 10, "canal": ["App"] * 10, "monto": [100.0] * 10,
    })
    inter = pd.DataFrame({
        "interaccion_id": ["I1", "I2", "I3"], "cliente_id": ["C1", "C1", "C2"],
        "fecha": ["2026-03-01"] * 3, "tipo": ["Queja", "Consulta", "Reclamo"],
        "canal": ["App"] * 3, "resuelta": [0, 1, 1],
    })
    gold = construir_features(clientes, trx, inter).set_index("cliente_id")

    c1 = gold.loc["C1"]
    assert c1["trx_12m"] == 10 and c1["trx_ult_3m"] == 1
    # (1/3) / (9/9) = 0.333
    assert c1["tendencia_actividad"] == pytest.approx(0.333, abs=0.001)
    assert c1["quejas_12m"] == 1 and c1["quejas_no_resueltas"] == 1 and c1["consultas_12m"] == 1
    # C3 no tiene transacciones: queda en 0 y con 365 días sin transacciones
    assert gold.loc["C3", "trx_12m"] == 0 and gold.loc["C3", "dias_sin_trx"] == 365
    assert gold.isna().sum().sum() == 0


# ===========================================================================
# Métricas del modelo
# ===========================================================================
def test_calcular_metricas_con_resultado_conocido():
    """Con predicciones conocidas, las métricas dan los valores esperados."""
    y_real = np.array([0, 0, 0, 1, 1])
    prob = np.array([0.1, 0.2, 0.6, 0.7, 0.9])     # con umbral 0.5: un falso positivo
    m = calcular_metricas(y_real, prob, umbral=0.5)
    assert m["auc"] == 1.0                           # el orden de las probabilidades es perfecto
    assert m["matriz_confusion"] == {"vn": 2, "fp": 1, "fn": 0, "vp": 2}
    assert m["recall"] == 1.0
    assert m["precision"] == pytest.approx(2 / 3, abs=0.001)


# ===========================================================================
# API (con una base temporal, para no tocar la base real)
# ===========================================================================
@pytest.fixture
def cliente_api(tmp_path):
    ruta = tmp_path / "prueba.db"
    con = sqlite3.connect(ruta)
    pd.DataFrame([
        {"cliente_id": "C00001", "nombre": "Ana López", "segmento": "Masivo", "departamento": "Guatemala",
         "saldo_promedio": 1000.0, "prob_abandono": 0.80, "prediccion_abandono": 1, "nivel_riesgo": "Alto",
         "accion": "Resolver queja pendiente y llamada de seguimiento", "canal_contacto": "Llamada",
         "motivo": "Tiene quejas sin resolver", "prioridad": 1, "modelo": "Prueba",
         "fecha_prediccion": "2026-11-09T10:00:00"},
        {"cliente_id": "C00002", "nombre": "Luis Pérez", "segmento": "Premium", "departamento": "Petén",
         "saldo_promedio": 9000.0, "prob_abandono": 0.10, "prediccion_abandono": 0, "nivel_riesgo": "Bajo",
         "accion": "Sin acción: seguimiento normal", "canal_contacto": "Ninguno",
         "motivo": "Riesgo bajo", "prioridad": 3, "modelo": "Prueba",
         "fecha_prediccion": "2026-11-09T10:00:00"},
    ]).to_sql("gold_predicciones", con, index=False)
    con.close()

    def db_prueba():
        c = sqlite3.connect(ruta, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    api.app.dependency_overrides[api.obtener_db] = db_prueba
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def test_api_recomendacion_cliente_existente(cliente_api):
    """GET /recomendacion/{id} devuelve 200 con la predicción y la acción del cliente."""
    r = cliente_api.get("/recomendacion/C00001")
    assert r.status_code == 200
    datos = r.json()
    assert datos["nivel_riesgo"] == "Alto"
    assert datos["prob_abandono"] == 0.80
    assert datos["accion"].startswith("Resolver queja")


def test_api_recomendacion_cliente_inexistente(cliente_api):
    """GET /recomendacion/{id} devuelve 404 si el cliente no existe."""
    r = cliente_api.get("/recomendacion/C99999")
    assert r.status_code == 404
    assert "no encontrado" in r.json()["detail"]


def test_api_registrar_accion_y_excluir_de_pendientes(cliente_api):
    """POST /acciones guarda la acción (201) y el cliente sale de la lista de pendientes."""
    antes = cliente_api.get("/clientes/alto-riesgo").json()
    assert [c["cliente_id"] for c in antes["clientes"]] == ["C00001"]

    r = cliente_api.post("/acciones", json={"cliente_id": "C00001", "detalle": "prueba"})
    assert r.status_code == 201
    assert r.json()["accion"].startswith("Resolver queja")   # usa la acción recomendada
    assert r.json()["estado"] == "Ejecutada"

    despues = cliente_api.get("/clientes/alto-riesgo").json()
    assert despues["total"] == 0
    assert len(cliente_api.get("/acciones").json()) == 1


def test_api_rechaza_acciones_invalidas(cliente_api):
    """POST /acciones rechaza un estado no válido (422) y un cliente inexistente (404)."""
    assert cliente_api.post("/acciones", json={"cliente_id": "C00001", "estado": "Hecho"}).status_code == 422
    assert cliente_api.post("/acciones", json={"cliente_id": "C99999"}).status_code == 404


def test_api_health_y_resumen(cliente_api):
    """/health indica que hay predicciones y /resumen calcula los indicadores."""
    assert cliente_api.get("/health").json()["predicciones"] == 2
    resumen = cliente_api.get("/resumen").json()
    assert resumen["total_clientes"] == 2
    assert resumen["pct_alto_riesgo"] == 0.5
    assert resumen["saldo_en_riesgo_alto"] == 1000.0


def test_api_exportar_powerbi(cliente_api, monkeypatch):
    """POST /powerbi/exportar devuelve los archivos generados (la exportación se simula)."""
    monkeypatch.setattr(api, "exportar_powerbi_csv", lambda: {"clientes_predicciones": 2})
    r = cliente_api.post("/powerbi/exportar")
    assert r.status_code == 200
    assert r.json()["archivos"] == {"clientes_predicciones": 2}
