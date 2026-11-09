"""
Parte 1 - Validación de los datos sintéticos.

Revisa los CSV de data/raw/ y genera:
  - reports/validacion_datos.md   (reporte con todas las revisiones)
  - reports/figuras/01_distribuciones_clientes.png
  - reports/figuras/02_actividad_y_abandono.png

Revisiones: conteo de registros, rangos, categorías válidas, nulos,
duplicados, integridad referencial (cada transacción tiene su cliente)
y distribuciones.

Uso:  python -m src.validar_datos
"""
import matplotlib
matplotlib.use("Agg")  # genera las imágenes sin abrir ventanas
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import config
from src.generar_datos import DEPARTAMENTOS, TIPOS_TRANSACCION

# Reglas de validación ------------------------------------------------------
RANGOS = {
    "clientes": {
        "edad": (18, 80),
        "ingreso_mensual": (3600, 80000),
        "antiguedad_meses": (1, 240),
        "num_productos": (1, 6),
        "tiene_tarjeta_credito": (0, 1),
        "tiene_prestamo": (0, 1),
        "saldo_promedio": (0, 5_000_000),
        "score_crediticio": (300, 850),
        "abandono": (0, 1),
    },
    "transacciones": {"monto": (10, 500_000)},
    "interacciones": {"resuelta": (0, 1)},
}

CATEGORIAS = {
    "clientes": {
        "genero": {"F", "M"},
        "segmento": {"Masivo", "Preferente", "Premium"},
        "departamento": set(DEPARTAMENTOS),
        "canal_preferido": {"App", "Web", "Agencia"},
    },
    "transacciones": {
        "tipo": set(TIPOS_TRANSACCION),
        "canal": {"App", "Web", "Agencia", "ATM", "POS"},
    },
    "interacciones": {
        "tipo": {"Consulta", "Queja", "Reclamo"},
        "canal": {"Call center", "App", "Agencia"},
    },
}

LLAVES = {"clientes": "cliente_id", "transacciones": "transaccion_id", "interacciones": "interaccion_id"}


def cargar():
    return {
        "clientes": pd.read_csv(config.DATA_RAW / "clientes.csv"),
        "transacciones": pd.read_csv(config.DATA_RAW / "transacciones.csv", parse_dates=["fecha"]),
        "interacciones": pd.read_csv(config.DATA_RAW / "interacciones.csv", parse_dates=["fecha"]),
    }


def estado(ok):
    return "OK" if ok else "ALERTA"


def validar(tablas):
    """Devuelve una lista de filas (revisión, tabla, detalle, resultado)."""
    res = []

    # 1. Conteo de registros
    n_cli = len(tablas["clientes"])
    res.append(("Conteo", "clientes", f"{n_cli:,} registros (mínimo 1,000)", estado(n_cli >= 1000)))
    for t in ["transacciones", "interacciones"]:
        res.append(("Conteo", t, f"{len(tablas[t]):,} registros", estado(len(tablas[t]) > 0)))

    # 2. Rangos (sin contar nulos)
    for t, reglas in RANGOS.items():
        for col, (mn, mx) in reglas.items():
            serie = tablas[t][col].dropna()
            fuera = int(((serie < mn) | (serie > mx)).sum())
            res.append(("Rango", t, f"{col} entre {mn:,} y {mx:,}: {fuera} fuera de rango", estado(fuera == 0)))

    # Fechas dentro de la ventana observada
    ini, fin = pd.Timestamp(config.FECHA_INICIO), pd.Timestamp(config.FECHA_CORTE) + pd.Timedelta(days=1)
    for t in ["transacciones", "interacciones"]:
        f = tablas[t]["fecha"]
        fuera = int(((f < ini) | (f >= fin)).sum())
        res.append(("Rango", t, f"fecha entre {config.FECHA_INICIO} y {config.FECHA_CORTE}: {fuera} fuera", estado(fuera == 0)))

    # 3. Categorías válidas
    for t, reglas in CATEGORIAS.items():
        for col, validas in reglas.items():
            invalidas = int((~tablas[t][col].dropna().isin(validas)).sum())
            res.append(("Categorías", t, f"{col}: {invalidas} valores no válidos", estado(invalidas == 0)))

    # 4. Nulos
    for t, df in tablas.items():
        nulos = df.isna().sum()
        nulos = nulos[nulos > 0]
        if nulos.empty:
            res.append(("Nulos", t, "sin nulos", "OK"))
        else:
            detalle = ", ".join(f"{c}: {v} ({v / len(df):.1%})" for c, v in nulos.items())
            res.append(("Nulos", t, detalle, "ALERTA"))

    # 5. Duplicados
    for t, df in tablas.items():
        dup_llave = int(df[LLAVES[t]].duplicated().sum())
        res.append(("Duplicados", t, f"{dup_llave} {LLAVES[t]} repetidos", estado(dup_llave == 0)))

    # 6. Integridad referencial
    ids = set(tablas["clientes"]["cliente_id"])
    for t in ["transacciones", "interacciones"]:
        huerfanos = int((~tablas[t]["cliente_id"].isin(ids)).sum())
        res.append(("Integridad", t, f"{huerfanos} registros sin cliente existente", estado(huerfanos == 0)))

    return res


def graficar(tablas):
    config.FIGURAS_DIR.mkdir(parents=True, exist_ok=True)
    cli, trx = tablas["clientes"], tablas["transacciones"]
    color = "#1f4e79"

    # Figura 1: distribuciones de clientes
    fig, ax = plt.subplots(2, 3, figsize=(15, 8))
    ax[0, 0].hist(cli["edad"], bins=30, color=color)
    ax[0, 0].set_title("Edad (años)")
    ax[0, 1].hist(cli["ingreso_mensual"].dropna(), bins=40, color=color)
    ax[0, 1].set_title("Ingreso mensual (Q)")
    ax[0, 2].hist(cli["antiguedad_meses"], bins=40, color=color)
    ax[0, 2].set_title("Antigüedad (meses)")
    ax[1, 0].hist(np.log10(cli["saldo_promedio"]), bins=40, color=color)
    ax[1, 0].set_title("Saldo promedio (log10 Q)")
    ax[1, 1].hist(cli["score_crediticio"], bins=30, color=color)
    ax[1, 1].set_title("Score crediticio")
    cli["num_productos"].value_counts().sort_index().plot.bar(ax=ax[1, 2], color=color)
    ax[1, 2].set_title("Número de productos")
    ax[1, 2].tick_params(axis="x", rotation=0)
    fig.suptitle(f"Distribuciones de los {len(cli):,} clientes sintéticos", fontsize=14)
    fig.tight_layout()
    fig.savefig(config.FIGURAS_DIR / "01_distribuciones_clientes.png", dpi=120)
    plt.close(fig)

    # Figura 2: actividad y abandono
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    trx.set_index("fecha").resample("MS").size().plot(ax=ax[0, 0], marker="o", color=color)
    ax[0, 0].set_title("Transacciones por mes")
    ax[0, 0].set_xlabel("")

    trx.boxplot(column="monto", by="tipo", ax=ax[0, 1], showfliers=False)
    ax[0, 1].set_title("Monto por tipo de transacción (Q, sin atípicos)")
    ax[0, 1].set_xlabel("")
    ax[0, 1].tick_params(axis="x", rotation=15)

    (cli.groupby("segmento")["abandono"].mean() * 100).plot.bar(ax=ax[1, 0], color=["#c0504d", "#f79646", "#9bbb59"])
    ax[1, 0].set_title(f"Tasa de abandono por segmento (%) — total {cli['abandono'].mean():.1%}")
    ax[1, 0].set_xlabel("")
    ax[1, 0].tick_params(axis="x", rotation=0)

    # Actividad mensual promedio por cliente: abandona vs se queda
    t = trx.merge(cli[["cliente_id", "abandono"]], on="cliente_id")
    mensual = t.groupby([t["fecha"].dt.to_period("M"), "abandono"]).size().unstack()
    mensual = mensual / cli["abandono"].value_counts()
    mensual.index = mensual.index.to_timestamp()
    mensual.columns = ["Se queda", "Abandona"]
    mensual.plot(ax=ax[1, 1], marker="o", color=["#9bbb59", "#c0504d"])
    ax[1, 1].set_title("Transacciones promedio por cliente al mes")
    ax[1, 1].set_xlabel("")

    fig.suptitle("Actividad transaccional y abandono", fontsize=14)
    fig.tight_layout()
    fig.savefig(config.FIGURAS_DIR / "02_actividad_y_abandono.png", dpi=120)
    plt.close(fig)


def escribir_reporte(tablas, resultados):
    cli = tablas["clientes"]
    lineas = [
        "# Reporte de validación de datos sintéticos",
        "",
        f"- Clientes: **{len(cli):,}** | Transacciones: **{len(tablas['transacciones']):,}** "
        f"| Interacciones: **{len(tablas['interacciones']):,}**",
        f"- Ventana observada: {config.FECHA_INICIO} a {config.FECHA_CORTE}",
        f"- Tasa de abandono: **{cli['abandono'].mean():.1%}**",
        "",
        "> Las ALERTAS de nulos y duplicados son esperadas: se simularon errores típicos",
        "> de los sistemas fuente y se corrigen en la capa Silver.",
        "",
        "## Resultados",
        "",
        "| Revisión | Tabla | Detalle | Resultado |",
        "|---|---|---|---|",
    ]
    lineas += [f"| {r} | {t} | {d} | {e} |" for r, t, d, e in resultados]

    lineas += ["", "## Estadísticas descriptivas (clientes)", "", "| Variable | Media | Mín | Mediana | Máx |", "|---|---|---|---|---|"]
    for col in ["edad", "ingreso_mensual", "antiguedad_meses", "num_productos", "saldo_promedio", "score_crediticio"]:
        s = cli[col]
        lineas.append(f"| {col} | {s.mean():,.1f} | {s.min():,.0f} | {s.median():,.0f} | {s.max():,.0f} |")

    lineas += ["", "## Distribuciones", "",
               "![Distribuciones](figuras/01_distribuciones_clientes.png)", "",
               "![Actividad y abandono](figuras/02_actividad_y_abandono.png)", ""]

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_DIR / "validacion_datos.md").write_text("\n".join(lineas), encoding="utf-8")


def main():
    tablas = cargar()
    resultados = validar(tablas)

    print(f"{'REVISIÓN':<12}{'TABLA':<15}{'RESULTADO':<10}DETALLE")
    for r, t, d, e in resultados:
        print(f"{r:<12}{t:<15}{e:<10}{d}")

    graficar(tablas)
    escribir_reporte(tablas, resultados)
    alertas = sum(e == "ALERTA" for *_, e in resultados)
    print(f"\n{len(resultados)} revisiones, {alertas} alertas (nulos/duplicados esperados, se limpian en Silver)")
    print(f"Reporte: {config.REPORTS_DIR / 'validacion_datos.md'}")


if __name__ == "__main__":
    main()
