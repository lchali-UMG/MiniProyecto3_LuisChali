"""Funciones de apoyo para trabajar con la base de datos SQLite."""
import sqlite3
from datetime import datetime

import pandas as pd

from src import config


def conectar(ruta=None):
    """Abre una conexión a la base SQLite (la crea si no existe)."""
    ruta = ruta or config.DB_PATH
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(ruta)


def leer_tabla(con, tabla):
    return pd.read_sql_query(f"SELECT * FROM {tabla}", con)


def guardar_tabla(con, df, tabla):
    """Guarda un DataFrame como tabla (carga completa: reemplaza lo anterior)."""
    df.to_sql(tabla, con, if_exists="replace", index=False)


def registrar_control(con, capa, tabla, entrada, salida, detalle=""):
    """Bitácora de cargas: qué tabla se cargó, cuántas filas y cuándo."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS control_cargas (
            fecha_proceso TEXT, capa TEXT, tabla TEXT,
            registros_entrada INTEGER, registros_salida INTEGER, detalle TEXT
        )""")
    con.execute(
        "INSERT INTO control_cargas VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), capa, tabla, int(entrada), int(salida), detalle),
    )
    con.commit()


def crear_tabla_acciones(con):
    """
    Tabla Gold donde se registran las acciones ejecutadas (por el robot de
    UiPath o manualmente). No se borra al volver a correr el pipeline.
    """
    con.execute("""
        CREATE TABLE IF NOT EXISTS gold_acciones_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_registro TEXT NOT NULL,
            cliente_id TEXT NOT NULL,
            nivel_riesgo TEXT,
            prob_abandono REAL,
            accion TEXT NOT NULL,
            canal_contacto TEXT,
            estado TEXT NOT NULL,
            ejecutado_por TEXT NOT NULL,
            detalle TEXT
        )""")
    con.commit()
