"""
Parte 2 - Capa BRONZE: ingesta de los CSV a SQLite tal como llegan.

En Bronze los datos se guardan "crudos": todas las columnas como texto, sin
limpiar, para tener una copia fiel de lo que mandó el sistema fuente.
Se agregan dos columnas de control:
  - _archivo_origen : de qué archivo vino el registro
  - _fecha_carga    : cuándo se cargó

Uso:  python -m src.ingesta
"""
from datetime import datetime

import pandas as pd

from src import config
from src.db import conectar, guardar_tabla, registrar_control


def ingestar_archivo(con, nombre, archivo):
    ruta = config.DATA_RAW / archivo
    # dtype=str -> todo se guarda como texto (los nulos quedan como NULL)
    df = pd.read_csv(ruta, dtype=str, encoding="utf-8")
    filas_archivo = len(df)

    df["_archivo_origen"] = archivo
    df["_fecha_carga"] = datetime.now().isoformat(timespec="seconds")

    tabla = f"bronze_{nombre}"
    guardar_tabla(con, df, tabla)
    registrar_control(con, "bronze", tabla, filas_archivo, len(df), f"origen: {archivo}")
    return tabla, filas_archivo


def main():
    con = conectar()
    print("BRONZE - ingesta de archivos fuente")
    for nombre, archivo in config.FUENTES.items():
        tabla, n = ingestar_archivo(con, nombre, archivo)
        print(f"  {archivo:<20} -> {tabla:<24} {n:>7,} filas")
    con.close()


if __name__ == "__main__":
    main()
