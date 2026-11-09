"""
Parte 2 - Capas SILVER y GOLD.

SILVER (datos limpios y con tipos correctos):
  - Convierte cada columna a su tipo (números, fechas, enteros).
  - Elimina transacciones duplicadas.
  - Imputa nulos: ingreso -> mediana de su segmento; canales -> moda o "Desconocido".
  - Descarta registros sin cliente válido o con montos no válidos.

GOLD (datos listos para el modelo, la API y Power BI):
  - gold_features_cliente: una fila por cliente con su perfil, su actividad
    de los últimos 12 meses, sus quejas y la variable objetivo `abandono`.

Las funciones de limpieza reciben y devuelven DataFrames, así se pueden
probar por separado con pytest.

Uso:  python -m src.transformar
"""
import pandas as pd

from src import config
from src.db import conectar, guardar_tabla, leer_tabla, registrar_control

COLUMNAS_CONTROL = ["_archivo_origen", "_fecha_carga"]


# ---------------------------------------------------------------------------
# SILVER
# ---------------------------------------------------------------------------
def limpiar_clientes(df):
    """Devuelve (clientes_limpios, detalle_de_lo_que_se_hizo)."""
    df = df.drop(columns=COLUMNAS_CONTROL, errors="ignore").copy()
    entrada = len(df)

    # Tipos
    enteros = ["edad", "antiguedad_meses", "num_productos", "tiene_tarjeta_credito",
               "tiene_prestamo", "score_crediticio", "abandono"]
    for col in enteros:
        df[col] = pd.to_numeric(df[col]).astype("int64")
    for col in ["ingreso_mensual", "saldo_promedio"]:
        df[col] = pd.to_numeric(df[col])
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"]).dt.strftime("%Y-%m-%d")
    for col in ["cliente_id", "nombre", "genero", "departamento", "segmento", "canal_preferido"]:
        df[col] = df[col].str.strip()

    # Duplicados por llave
    df = df.drop_duplicates(subset="cliente_id", keep="first")
    duplicados = entrada - len(df)

    # Nulos: ingreso -> mediana de su segmento
    nulos_ingreso = int(df["ingreso_mensual"].isna().sum())
    mediana_seg = df.groupby("segmento")["ingreso_mensual"].transform("median")
    df["ingreso_mensual"] = df["ingreso_mensual"].fillna(mediana_seg).round(2)

    # Nulos: canal preferido -> el canal más común (moda)
    nulos_canal = int(df["canal_preferido"].isna().sum())
    df["canal_preferido"] = df["canal_preferido"].fillna(df["canal_preferido"].mode()[0])

    detalle = (f"duplicados eliminados: {duplicados}; ingreso imputado: {nulos_ingreso}; "
               f"canal imputado: {nulos_canal}")
    return df.reset_index(drop=True), detalle


def limpiar_transacciones(df, ids_clientes):
    df = df.drop(columns=COLUMNAS_CONTROL, errors="ignore").copy()
    entrada = len(df)

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["monto"] = pd.to_numeric(df["monto"])

    # Duplicados (doble carga del sistema fuente)
    df = df.drop_duplicates(subset="transaccion_id", keep="first")
    duplicados = entrada - len(df)

    # Nulos en canal -> "Desconocido" (no se puede adivinar el canal real)
    nulos_canal = int(df["canal"].isna().sum())
    df["canal"] = df["canal"].fillna("Desconocido")

    # Registros no válidos: cliente inexistente o monto <= 0
    validos = df["cliente_id"].isin(ids_clientes) & (df["monto"] > 0)
    invalidos = int((~validos).sum())
    df = df[validos]

    df["fecha"] = df["fecha"].dt.strftime("%Y-%m-%d %H:%M:%S")
    detalle = (f"duplicados eliminados: {duplicados}; canal imputado: {nulos_canal}; "
               f"registros inválidos descartados: {invalidos}")
    return df.reset_index(drop=True), detalle


def limpiar_interacciones(df, ids_clientes):
    df = df.drop(columns=COLUMNAS_CONTROL, errors="ignore").copy()
    entrada = len(df)

    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%Y-%m-%d")
    df["resuelta"] = pd.to_numeric(df["resuelta"]).astype("int64")
    df = df.drop_duplicates(subset="interaccion_id", keep="first")
    duplicados = entrada - len(df)
    df = df[df["cliente_id"].isin(ids_clientes)]

    detalle = f"duplicados eliminados: {duplicados}; descartados: {entrada - duplicados - len(df)}"
    return df.reset_index(drop=True), detalle


# ---------------------------------------------------------------------------
# GOLD
# ---------------------------------------------------------------------------
def construir_features(clientes, trx, inter):
    """Una fila por cliente con todas las variables para el modelo."""
    trx = trx.copy()
    trx["fecha"] = pd.to_datetime(trx["fecha"])
    reciente = trx["fecha"] >= pd.Timestamp(config.FECHA_INICIO_RECIENTE)
    trx["reciente"] = reciente.astype(int)
    trx["digital"] = trx["canal"].isin(["App", "Web"]).astype(int)

    act = trx.groupby("cliente_id").agg(
        trx_12m=("transaccion_id", "count"),
        monto_12m=("monto", "sum"),
        trx_ult_3m=("reciente", "sum"),
        pct_digital=("digital", "mean"),
        tipos_distintos=("tipo", "nunique"),
        ultima_trx=("fecha", "max"),
    )
    # Tendencia: promedio mensual de los últimos 3 meses vs. los 9 anteriores
    prom_reciente = act["trx_ult_3m"] / 3
    prom_anterior = (act["trx_12m"] - act["trx_ult_3m"]) / 9
    act["tendencia_actividad"] = (prom_reciente / prom_anterior.where(prom_anterior > 0)).fillna(0).round(3)
    act["dias_sin_trx"] = (pd.Timestamp(config.FECHA_CORTE) - act["ultima_trx"]).dt.days
    act = act.drop(columns="ultima_trx")

    quejas = inter[inter["tipo"].isin(["Queja", "Reclamo"])]
    serv = pd.DataFrame({
        "consultas_12m": inter[inter["tipo"] == "Consulta"].groupby("cliente_id").size(),
        "quejas_12m": quejas.groupby("cliente_id").size(),
        "quejas_no_resueltas": quejas[quejas["resuelta"] == 0].groupby("cliente_id").size(),
    })

    gold = clientes.set_index("cliente_id").join(act).join(serv)

    # Clientes sin transacciones o sin quejas -> 0
    cero = ["trx_12m", "monto_12m", "trx_ult_3m", "pct_digital", "tipos_distintos",
            "tendencia_actividad", "consultas_12m", "quejas_12m", "quejas_no_resueltas"]
    gold[cero] = gold[cero].fillna(0)
    gold["dias_sin_trx"] = gold["dias_sin_trx"].fillna(365)

    enteros = ["trx_12m", "trx_ult_3m", "tipos_distintos", "dias_sin_trx",
               "consultas_12m", "quejas_12m", "quejas_no_resueltas"]
    gold[enteros] = gold[enteros].astype("int64")
    gold["monto_12m"] = gold["monto_12m"].round(2)
    gold["pct_digital"] = gold["pct_digital"].round(3)

    # La variable objetivo va al final
    cols = [c for c in gold.columns if c != "abandono"] + ["abandono"]
    return gold[cols].reset_index()


def main():
    con = conectar()

    print("SILVER - limpieza y tipado")
    b_cli = leer_tabla(con, "bronze_clientes")
    b_trx = leer_tabla(con, "bronze_transacciones")
    b_int = leer_tabla(con, "bronze_interacciones")

    s_cli, d_cli = limpiar_clientes(b_cli)
    ids = set(s_cli["cliente_id"])
    s_trx, d_trx = limpiar_transacciones(b_trx, ids)
    s_int, d_int = limpiar_interacciones(b_int, ids)

    for tabla, bronze, silver, detalle in [
        ("silver_clientes", b_cli, s_cli, d_cli),
        ("silver_transacciones", b_trx, s_trx, d_trx),
        ("silver_interacciones", b_int, s_int, d_int),
    ]:
        guardar_tabla(con, silver, tabla)
        registrar_control(con, "silver", tabla, len(bronze), len(silver), detalle)
        print(f"  {tabla:<24} {len(bronze):>7,} -> {len(silver):>7,}  ({detalle})")

    print("GOLD - variables por cliente")
    gold = construir_features(s_cli, s_trx, s_int)
    guardar_tabla(con, gold, "gold_features_cliente")
    registrar_control(con, "gold", "gold_features_cliente", len(s_cli), len(gold),
                      f"{gold.shape[1]} columnas")
    print(f"  gold_features_cliente    {len(gold):>7,} clientes x {gold.shape[1]} columnas")
    con.close()


if __name__ == "__main__":
    main()
