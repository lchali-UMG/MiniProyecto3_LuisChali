"""
Parte 8 - Exportación de la capa Gold a CSV para Power BI.

Genera en powerbi/datos/:
  - clientes_predicciones.csv  1 fila por cliente: perfil, comportamiento, predicción,
                               acción recomendada y estado de contacto (según el robot)
  - acciones_log.csv           acciones registradas por el robot de UiPath
  - actividad_mensual.csv      transacciones por mes y nivel de riesgo (la "historia")
  - metricas_modelo.csv        AUC, F1, precisión, recall y exactitud del modelo
  - importancia_variables.csv  variables que más influyen en el abandono

Los CSV se escriben en UTF-8 con BOM para que Power BI lea bien las tildes.
Lo ejecuta run_pipeline.py, el endpoint POST /powerbi/exportar (lo llama el
robot de UiPath) o manualmente:

Uso:  python -m src.exportar_powerbi
"""
import json

import pandas as pd

from src import config
from src.db import conectar, crear_tabla_acciones, registrar_control

POWERBI_DATOS = config.RAIZ / "powerbi" / "datos"

NOMBRES_METRICAS = {"auc": "AUC", "f1": "F1", "precision": "Precisión",
                    "recall": "Recall (sensibilidad)", "exactitud": "Exactitud"}


def tipo_gestion(detalle):
    detalle = str(detalle or "")
    if detalle.startswith("URGENTE"):
        return "Urgente"
    if detalle.startswith("Campaña"):
        return "Campaña"
    return "Otra"


def tabla_clientes(con, acciones):
    pred = pd.read_sql_query("SELECT * FROM gold_predicciones", con)
    feat = pd.read_sql_query(
        """SELECT cliente_id, genero, ingreso_mensual, antiguedad_meses, tiene_tarjeta_credito,
                  tiene_prestamo, score_crediticio, trx_12m, monto_12m, trx_ult_3m, pct_digital,
                  dias_sin_trx, consultas_12m, quejas_12m
           FROM gold_features_cliente""", con)
    df = pred.merge(feat, on="cliente_id", how="left")

    # Último contacto registrado por el robot para cada cliente
    ejecutadas = acciones[acciones["estado"] == "Ejecutada"]
    ultimo = (ejecutadas.sort_values("fecha_registro")
              .groupby("cliente_id")
              .agg(fecha_contacto=("fecha_registro", "last"), tipo_gestion=("tipo_gestion", "last")))
    df = df.merge(ultimo, on="cliente_id", how="left")

    df["contactado"] = df["fecha_contacto"].notna().astype(int)
    df["estado_contacto"] = "Pendiente"
    df.loc[df["prioridad"] == 3, "estado_contacto"] = "No requiere acción"
    df.loc[df["contactado"] == 1, "estado_contacto"] = "Contactado por el robot"
    df["tipo_gestion"] = df["tipo_gestion"].fillna("")
    df["fecha_contacto"] = df["fecha_contacto"].fillna("")
    df["orden_riesgo"] = df["nivel_riesgo"].map({"Alto": 1, "Medio": 2, "Bajo": 3})
    return df


def tabla_actividad(con):
    trx = pd.read_sql_query(
        """SELECT t.cliente_id, substr(t.fecha, 1, 7) AS mes, t.monto, p.nivel_riesgo
           FROM silver_transacciones t
           JOIN gold_predicciones p ON p.cliente_id = t.cliente_id""", con)
    clientes_nivel = pd.read_sql_query(
        "SELECT nivel_riesgo, COUNT(*) AS clientes_nivel FROM gold_predicciones GROUP BY nivel_riesgo", con)
    act = (trx.groupby(["mes", "nivel_riesgo"])
           .agg(transacciones=("monto", "size"), monto=("monto", "sum"),
                clientes_activos=("cliente_id", "nunique"))
           .reset_index()
           .merge(clientes_nivel, on="nivel_riesgo"))
    act["trx_por_cliente"] = (act["transacciones"] / act["clientes_nivel"]).round(3)
    act["monto"] = act["monto"].round(2)
    act["fecha_mes"] = act["mes"] + "-01"
    act["orden_riesgo"] = act["nivel_riesgo"].map({"Alto": 1, "Medio": 2, "Bajo": 3})
    return act


def tablas_modelo():
    archivo = config.REPORTS_DIR / "metricas_modelo.json"
    if not archivo.exists():
        return pd.DataFrame(), pd.DataFrame()
    m = json.loads(archivo.read_text(encoding="utf-8"))
    elegido = m["comparacion"][m["modelo_elegido"]]["prueba"]
    metricas = pd.DataFrame(
        [{"metrica": NOMBRES_METRICAS[k], "valor": elegido[k], "orden": i}
         for i, k in enumerate(NOMBRES_METRICAS, 1)])
    metricas["modelo"] = m["modelo_elegido"]
    metricas["umbral"] = m["umbral"]
    importancia = pd.DataFrame(
        [{"variable": k, "importancia": v} for k, v in m["importancia_variables"].items()])
    return metricas, importancia


def exportar():
    con = conectar()
    crear_tabla_acciones(con)
    acciones = pd.read_sql_query("SELECT * FROM gold_acciones_log", con)
    acciones["tipo_gestion"] = acciones["detalle"].apply(tipo_gestion)
    acciones["fecha"] = acciones["fecha_registro"].str[:10]

    tablas = {
        "clientes_predicciones": tabla_clientes(con, acciones),
        "acciones_log": acciones,
        "actividad_mensual": tabla_actividad(con),
    }
    metricas, importancia = tablas_modelo()
    tablas["metricas_modelo"] = metricas
    tablas["importancia_variables"] = importancia

    POWERBI_DATOS.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for nombre, df in tablas.items():
        df.to_csv(POWERBI_DATOS / f"{nombre}.csv", index=False, encoding="utf-8-sig")
        resumen[nombre] = len(df)
    registrar_control(con, "powerbi", "csv_powerbi", sum(resumen.values()), sum(resumen.values()),
                      json.dumps(resumen))
    con.close()
    return resumen


def main():
    print("POWER BI - exportación de la capa Gold a CSV")
    for nombre, filas in exportar().items():
        print(f"  powerbi/datos/{nombre + '.csv':<28} {filas:>6,} filas")


if __name__ == "__main__":
    main()
