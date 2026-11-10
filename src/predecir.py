"""
Parte 4 - Predicción y acción recomendada para cada cliente.

  1. Carga el modelo entrenado (models/modelo_abandono.joblib).
  2. Calcula la probabilidad de abandono de los 1,500 clientes.
  3. Clasifica el riesgo: Alto / Medio / Bajo.
  4. Aplica la regla de negocio que recomienda una acción personalizada.
  5. Guarda todo en la capa Gold: tabla gold_predicciones.

Uso:  python -m src.predecir
"""
from datetime import datetime

import joblib
import pandas as pd

from src import config
from src.db import conectar, crear_tabla_acciones, guardar_tabla, leer_tabla, registrar_control
from src.modelo import ARCHIVO_MODELO

# Niveles de riesgo según la probabilidad de abandono
UMBRAL_ALTO = 0.45
UMBRAL_MEDIO = 0.20


def nivel_riesgo(prob):
    if prob >= UMBRAL_ALTO:
        return "Alto"
    if prob >= UMBRAL_MEDIO:
        return "Medio"
    return "Bajo"


def recomendar_accion(cliente):
    """
    Regla de negocio: a partir del riesgo y del perfil del cliente recomienda
    UNA acción concreta. Recibe un dict (o fila) con las variables de Gold y
    `nivel_riesgo`. Devuelve: accion, canal_contacto, motivo y prioridad (1 = urgente).
    """
    nivel = cliente["nivel_riesgo"]

    if nivel == "Alto":
        if cliente["quejas_no_resueltas"] > 0:
            return {"accion": "Resolver queja pendiente y llamada de seguimiento",
                    "canal_contacto": "Llamada", "motivo": "Tiene quejas sin resolver", "prioridad": 1}
        if cliente["segmento"] in ("Premium", "Preferente") or cliente["saldo_promedio"] >= 20000:
            return {"accion": "Llamada de asesor personal con oferta de retención",
                    "canal_contacto": "Llamada", "motivo": "Cliente de alto valor en riesgo", "prioridad": 1}
        if cliente["tendencia_actividad"] < 0.5 or cliente["dias_sin_trx"] > 30:
            return {"accion": "Campaña de reactivación: bono por transacciones en la app",
                    "canal_contacto": "Correo + notificación", "motivo": "Su actividad cayó en los últimos meses",
                    "prioridad": 1}
        return {"accion": "Oferta de retención: exoneración de comisiones por 3 meses",
                "canal_contacto": "Correo", "motivo": "Alto riesgo de abandono", "prioridad": 1}

    if nivel == "Medio":
        if cliente["num_productos"] == 1 and cliente["tiene_tarjeta_credito"] == 0:
            return {"accion": "Ofrecer tarjeta de crédito preaprobada (venta cruzada)",
                    "canal_contacto": "Correo", "motivo": "Solo tiene un producto con el banco", "prioridad": 2}
        if cliente["pct_digital"] < 0.3:
            return {"accion": "Invitar a usar la app con beneficio de bienvenida",
                    "canal_contacto": "SMS", "motivo": "Usa poco los canales digitales", "prioridad": 2}
        return {"accion": "Sugerir plan de ahorro programado",
                "canal_contacto": "Notificación en app", "motivo": "Riesgo medio de abandono", "prioridad": 2}

    return {"accion": "Sin acción: seguimiento normal",
            "canal_contacto": "Ninguno", "motivo": "Riesgo bajo", "prioridad": 3}


def predecir():
    paquete = joblib.load(ARCHIVO_MODELO)
    modelo, variables, umbral = paquete["modelo"], paquete["variables"], paquete["umbral"]
    ids_entrenamiento = set(paquete["ids_entrenamiento"])

    con = conectar()
    gold = leer_tabla(con, "gold_features_cliente")

    gold["prob_abandono"] = modelo.predict_proba(gold[variables])[:, 1].round(4)
    gold["prediccion_abandono"] = (gold["prob_abandono"] >= umbral).astype(int)
    gold["nivel_riesgo"] = gold["prob_abandono"].apply(nivel_riesgo)
    acciones = pd.DataFrame([recomendar_accion(fila) for fila in gold.to_dict("records")])
    gold = pd.concat([gold, acciones], axis=1)

    gold["conjunto"] = gold["cliente_id"].apply(
        lambda c: "entrenamiento" if c in ids_entrenamiento else "prueba")
    gold["modelo"] = paquete["nombre"]
    gold["fecha_prediccion"] = datetime.now().isoformat(timespec="seconds")

    columnas = [
        "cliente_id", "nombre", "segmento", "departamento", "edad", "canal_preferido",
        "saldo_promedio", "num_productos", "tendencia_actividad", "quejas_no_resueltas",
        "prob_abandono", "prediccion_abandono", "nivel_riesgo",
        "accion", "canal_contacto", "motivo", "prioridad",
        "abandono", "conjunto", "modelo", "fecha_prediccion",
    ]
    pred = gold[columnas].rename(columns={"abandono": "abandono_real"})
    pred = pred.sort_values("prob_abandono", ascending=False).reset_index(drop=True)

    guardar_tabla(con, pred, "gold_predicciones")
    crear_tabla_acciones(con)  # la bitácora de acciones queda lista para UiPath
    registrar_control(con, "gold", "gold_predicciones", len(gold), len(pred),
                      f"modelo: {paquete['nombre']}; umbral: {umbral}")
    con.close()
    return pred


def main():
    print("PREDICCIÓN - probabilidad de abandono y acción recomendada")
    pred = predecir()
    print(f"  gold_predicciones        {len(pred):>7,} clientes")
    resumen = pred.groupby("nivel_riesgo").agg(
        clientes=("cliente_id", "count"),
        prob_media=("prob_abandono", "mean"),
        abandono_real=("abandono_real", "mean"),
    ).reindex(["Alto", "Medio", "Bajo"])
    for nivel, r in resumen.iterrows():
        print(f"  Riesgo {nivel:<6} {int(r.clientes):>5} clientes | prob. media {r.prob_media:.1%}"
              f" | abandono real {r.abandono_real:.1%}")
    print("\n  Acciones recomendadas:")
    for accion, n in pred["accion"].value_counts().items():
        print(f"    {n:>5}  {accion}")


if __name__ == "__main__":
    main()
