"""
Borra la bitácora de acciones (gold_acciones_log) para empezar una demo desde cero.
Las predicciones NO se borran.

Uso:  python -m src.reiniciar_acciones
"""
from src.db import conectar, crear_tabla_acciones


def main():
    con = conectar()
    crear_tabla_acciones(con)
    n = con.execute("SELECT COUNT(*) FROM gold_acciones_log").fetchone()[0]
    con.execute("DELETE FROM gold_acciones_log")
    con.execute("DELETE FROM sqlite_sequence WHERE name = 'gold_acciones_log'")
    con.commit()
    con.close()
    print(f"Bitácora de acciones reiniciada ({n} registros borrados).")


if __name__ == "__main__":
    main()
