"""
Parte 1 - Generación de datos sintéticos para NovaBank.

Crea 3 archivos CSV en data/raw/ que simulan los sistemas fuente del banco:
  - clientes.csv       (core bancario / CRM)  -> 1 fila por cliente
  - transacciones.csv  (core transaccional)   -> movimientos de 12 meses
  - interacciones.csv  (call center / app)    -> consultas, quejas y reclamos

La variable objetivo es `abandono` (1 = el cliente cerró su relación con el
banco en los 90 días posteriores a la fecha de corte). Se genera a partir de
factores de riesgo realistas (poca antigüedad, pocos productos, quejas, etc.)
más ruido aleatorio, y los clientes que abandonan muestran una caída en su
actividad durante los últimos meses, como pasa en la vida real.

Uso:  python -m src.generar_datos
"""
from datetime import timedelta

import numpy as np
import pandas as pd

from src import config


DEPARTAMENTOS = {
    "Guatemala": 0.40, "Quetzaltenango": 0.10, "Sacatepéquez": 0.07,
    "Escuintla": 0.07, "Alta Verapaz": 0.06, "Huehuetenango": 0.06,
    "Petén": 0.05, "Chimaltenango": 0.05, "San Marcos": 0.05,
    "Zacapa": 0.05, "Izabal": 0.04,
}

NOMBRES_F = [
    "María", "Ana", "Sofía", "Lucía", "Gabriela", "Andrea", "Carmen", "Rosa",
    "Alejandra", "Daniela", "Valeria", "Fernanda", "Paola", "Mónica", "Claudia",
    "Silvia", "Patricia", "Karla", "Jennifer", "Mariana", "Elena", "Beatriz",
    "Lesly", "Ingrid", "Brenda", "Wendy", "Marta", "Juana", "Isabel", "Gloria",
]
NOMBRES_M = [
    "José", "Juan", "Luis", "Carlos", "Jorge", "Mario", "Pedro", "Miguel",
    "Diego", "Javier", "Fernando", "Ricardo", "Daniel", "Alejandro", "Andrés",
    "Pablo", "Sergio", "Óscar", "Edgar", "Byron", "Kevin", "Erick", "Walter",
    "Otto", "Héctor", "Rodrigo", "Julio", "Manuel", "Francisco", "Estuardo",
]
APELLIDOS = [
    "López", "García", "Pérez", "Hernández", "González", "Rodríguez", "Martínez",
    "Morales", "Ramírez", "Castillo", "Juárez", "Méndez", "Reyes", "Cruz",
    "Ortiz", "Mejía", "Chávez", "Orellana", "Barrios", "Ajú", "Xicará", "Coyoy",
    "Tzul", "Sic", "Batz", "Monterroso", "Arévalo", "Estrada", "Girón", "Pineda",
    "Velásquez", "Recinos", "Cifuentes", "Aguilar", "Fuentes", "Solís",
]

TIPOS_TRANSACCION = ["Deposito", "Retiro", "Transferencia", "Pago_servicio", "Compra_tarjeta"]


def sigmoide(x):
    return 1 / (1 + np.exp(-x))


# ---------------------------------------------------------------------------
# 1. Clientes
# ---------------------------------------------------------------------------
def generar_clientes(rng, n):
    corte = pd.Timestamp(config.FECHA_CORTE)

    # Edad: 18 años + distribución gamma (media ~40, cola hacia mayores)
    edad = np.clip(18 + rng.gamma(4, 5.5, n), 18, 80).astype(int)
    genero = rng.choice(["F", "M"], n)
    departamento = rng.choice(list(DEPARTAMENTOS), n, p=list(DEPARTAMENTOS.values()))

    # Ingreso mensual en quetzales: parte del salario mínimo (~Q3,600) más una
    # distribución log-normal (muchos ingresos bajos, pocos muy altos)
    ingreso = np.clip(3600 + rng.lognormal(np.log(4500), 0.7, n), 3600, 80000).round(2)
    segmento = np.where(ingreso >= 25000, "Premium",
                        np.where(ingreso >= 10000, "Preferente", "Masivo"))
    nivel_seg = pd.Series(segmento).map({"Masivo": 0, "Preferente": 1, "Premium": 2}).to_numpy()

    antiguedad = np.clip(rng.gamma(2, 30, n), 1, 240).astype(int)
    fecha_alta = [(corte - pd.DateOffset(months=int(m))).date() for m in antiguedad]

    num_productos = np.clip(1 + rng.poisson(0.8 + 0.5 * nivel_seg), 1, 6)
    tiene_tarjeta = rng.binomial(1, 0.35 + 0.20 * nivel_seg)
    tiene_prestamo = rng.binomial(1, 0.20 + 0.10 * nivel_seg)

    saldo = np.clip(ingreso * rng.lognormal(0, 0.7, n) * 0.8, 50, None).round(2)
    score = np.clip(rng.normal(650, 70, n) + 20 * nivel_seg, 300, 850).astype(int)

    # Los jóvenes prefieren la app; los mayores, la agencia
    p_app = np.clip(0.75 - 0.01 * (edad - 18), 0.15, 0.75)
    p_agencia = np.clip(0.10 + 0.01 * (edad - 18), 0.10, 0.65)
    p_web = 1 - p_app - p_agencia
    u = rng.random(n)
    canal = np.where(u < p_app, "App", np.where(u < p_app + p_web, "Web", "Agencia"))

    # Nombre coherente con el género + dos apellidos
    nombres = [
        f"{rng.choice(NOMBRES_F if g == 'F' else NOMBRES_M)} "
        f"{rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        for g in genero
    ]

    return pd.DataFrame({
        "cliente_id": [f"C{i:05d}" for i in range(1, n + 1)],
        "nombre": nombres,
        "genero": genero,
        "edad": edad,
        "departamento": departamento,
        "segmento": segmento,
        "ingreso_mensual": ingreso,
        "antiguedad_meses": antiguedad,
        "fecha_alta": fecha_alta,
        "num_productos": num_productos,
        "tiene_tarjeta_credito": tiene_tarjeta,
        "tiene_prestamo": tiene_prestamo,
        "saldo_promedio": saldo,
        "score_crediticio": score,
        "canal_preferido": canal,
    })


# ---------------------------------------------------------------------------
# 2. Variable objetivo: abandono
# ---------------------------------------------------------------------------
def asignar_abandono(rng, clientes):
    """Calcula una 'propensión' al abandono y sortea quién abandona."""
    n = len(clientes)
    # Número de quejas en el año (las quejas empujan al abandono)
    quejas = rng.poisson(0.6, n)

    log_saldo = np.log(clientes["saldo_promedio"])
    log_saldo = (log_saldo - log_saldo.mean()) / log_saldo.std()

    riesgo = (
        0.9 * (clientes["antiguedad_meses"] < 12)
        - 0.35 * (clientes["num_productos"] - 1)
        - 0.5 * clientes["tiene_tarjeta_credito"]
        - 0.4 * clientes["tiene_prestamo"]
        + 0.5 * (clientes["edad"] < 30)
        + 0.4 * (clientes["canal_preferido"] == "Agencia")
        - 0.4 * log_saldo
        + 0.55 * quejas
        + rng.normal(0, 0.8, n)          # ruido: no todo se puede explicar
    ).to_numpy()

    # Buscar el intercepto que deja la tasa de abandono cerca del objetivo
    bajo, alto = -10.0, 10.0
    for _ in range(50):
        medio = (bajo + alto) / 2
        if sigmoide(riesgo + medio).mean() > config.TASA_ABANDONO_OBJETIVO:
            alto = medio
        else:
            bajo = medio
    prob = sigmoide(riesgo + medio)

    clientes = clientes.copy()
    clientes["abandono"] = rng.binomial(1, prob)
    return clientes, quejas


# ---------------------------------------------------------------------------
# 3. Transacciones (12 meses)
# ---------------------------------------------------------------------------
def montos_por_tipo(rng, tipo, ingreso):
    if tipo == "Deposito":
        return ingreso * rng.uniform(0.2, 0.6)
    if tipo == "Retiro":
        return rng.lognormal(np.log(500), 0.7)
    if tipo == "Transferencia":
        return rng.lognormal(np.log(800), 0.9)
    if tipo == "Pago_servicio":
        return rng.lognormal(np.log(250), 0.5)
    return rng.lognormal(np.log(300), 0.9)  # Compra_tarjeta


def canal_por_tipo(rng, tipo, canal_pref):
    if tipo == "Retiro":
        return rng.choice(["ATM", "Agencia"], p=[0.8, 0.2])
    if tipo == "Compra_tarjeta":
        return "POS"
    # El resto se hace casi siempre por el canal preferido del cliente
    return canal_pref if rng.random() < 0.7 else rng.choice(["App", "Web", "Agencia"])


def generar_transacciones(rng, clientes):
    inicio = pd.Timestamp(config.FECHA_INICIO)
    meses = pd.date_range(inicio, periods=12, freq="MS")
    filas = []

    for c in clientes.itertuples(index=False):
        # Actividad base del cliente
        lam = (1 + 0.6 * c.num_productos + 1.0 * (c.canal_preferido == "App")) * rng.gamma(4, 0.25)

        # Los que abandonan reducen su actividad en los últimos 3 meses
        # (25 % se va "en silencio", sin señales previas)
        factores = rng.uniform(0.8, 1.2, 12)
        if c.abandono == 1 and rng.random() > 0.25:
            factores[-3:] = factores[-3:] * np.array([0.6, 0.4, 0.2])

        p_tipos = np.array([0.25, 0.20, 0.20, 0.20, 0.15])
        if c.tiene_tarjeta_credito == 0:
            p_tipos = np.array([0.30, 0.25, 0.22, 0.23, 0.0])

        for mes, factor in zip(meses, factores):
            n_mes = rng.poisson(lam * factor)
            dias_mes = mes.days_in_month
            for _ in range(n_mes):
                tipo = rng.choice(TIPOS_TRANSACCION, p=p_tipos)
                fecha = mes + timedelta(days=int(rng.integers(0, dias_mes)),
                                           minutes=int(rng.integers(6 * 60, 22 * 60)))
                monto = max(10.0, montos_por_tipo(rng, tipo, c.ingreso_mensual))
                filas.append((c.cliente_id, fecha, tipo,
                              canal_por_tipo(rng, tipo, c.canal_preferido), round(monto, 2)))

    trx = pd.DataFrame(filas, columns=["cliente_id", "fecha", "tipo", "canal", "monto"])
    trx = trx.sort_values("fecha").reset_index(drop=True)
    trx.insert(0, "transaccion_id", [f"T{i:07d}" for i in range(1, len(trx) + 1)])
    return trx


# ---------------------------------------------------------------------------
# 4. Interacciones con servicio al cliente
# ---------------------------------------------------------------------------
def generar_interacciones(rng, clientes, quejas):
    inicio = pd.Timestamp(config.FECHA_INICIO)
    dias_ventana = (pd.Timestamp(config.FECHA_CORTE) - inicio).days
    filas = []

    for c, n_quejas in zip(clientes.itertuples(index=False), quejas):
        n_consultas = rng.poisson(1.5)
        tipos = ["Consulta"] * n_consultas + list(rng.choice(["Queja", "Reclamo"], n_quejas, p=[0.7, 0.3]))
        for tipo in tipos:
            fecha = inicio + timedelta(days=int(rng.integers(0, dias_ventana + 1)))
            if tipo == "Consulta":
                p_resuelta = 0.95
            else:
                # A los que abandonan se les resuelven menos quejas
                p_resuelta = 0.50 if c.abandono == 1 else 0.85
            filas.append((c.cliente_id, fecha.date(), tipo,
                          rng.choice(["Call center", "App", "Agencia"], p=[0.5, 0.3, 0.2]),
                          int(rng.random() < p_resuelta)))

    inter = pd.DataFrame(filas, columns=["cliente_id", "fecha", "tipo", "canal", "resuelta"])
    inter = inter.sort_values("fecha").reset_index(drop=True)
    inter.insert(0, "interaccion_id", [f"I{i:06d}" for i in range(1, len(inter) + 1)])
    return inter


# ---------------------------------------------------------------------------
# 5. Errores típicos de sistemas fuente (para que Silver tenga algo que limpiar)
# ---------------------------------------------------------------------------
def inyectar_errores(rng, clientes, trx):
    clientes = clientes.copy()
    trx = trx.copy()

    # ~1 % de nulos en ingreso y en canal preferido
    for col in ["ingreso_mensual", "canal_preferido"]:
        idx = rng.choice(clientes.index, int(len(clientes) * 0.01), replace=False)
        clientes.loc[idx, col] = np.nan

    # ~0.3 % de nulos en el canal de la transacción
    idx = rng.choice(trx.index, int(len(trx) * 0.003), replace=False)
    trx.loc[idx, "canal"] = np.nan

    # ~0.5 % de transacciones duplicadas (doble carga del sistema fuente)
    dup = trx.sample(frac=0.005, random_state=config.SEMILLA)
    trx = pd.concat([trx, dup]).sort_values("fecha").reset_index(drop=True)
    return clientes, trx


def main():
    rng = np.random.default_rng(config.SEMILLA)

    print("Generando clientes...")
    clientes = generar_clientes(rng, config.N_CLIENTES)
    clientes, quejas = asignar_abandono(rng, clientes)

    print("Generando transacciones (12 meses)...")
    trx = generar_transacciones(rng, clientes)

    print("Generando interacciones...")
    inter = generar_interacciones(rng, clientes, quejas)

    if config.INYECTAR_ERRORES:
        clientes, trx = inyectar_errores(rng, clientes, trx)

    config.DATA_RAW.mkdir(parents=True, exist_ok=True)
    clientes.to_csv(config.DATA_RAW / "clientes.csv", index=False, encoding="utf-8")
    trx.to_csv(config.DATA_RAW / "transacciones.csv", index=False, encoding="utf-8")
    inter.to_csv(config.DATA_RAW / "interacciones.csv", index=False, encoding="utf-8")

    print(f"Listo -> {config.DATA_RAW}")
    print(f"  clientes:      {len(clientes):>7,} filas  (tasa de abandono {clientes['abandono'].mean():.1%})")
    print(f"  transacciones: {len(trx):>7,} filas")
    print(f"  interacciones: {len(inter):>7,} filas")


if __name__ == "__main__":
    main()
