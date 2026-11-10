"""
Parte 5 - API de hiperpersonalización de NovaBank (FastAPI).

Expone las predicciones de la capa Gold para que otros sistemas (el robot de
UiPath, la app del banco, el call center) las consuman.

Endpoints:
  GET  /health                       estado de la API y de la base de datos
  GET  /recomendacion/{cliente_id}   predicción y acción recomendada de un cliente
  GET  /clientes/alto-riesgo         lista de clientes a contactar (para UiPath)
  POST /acciones                     registra una acción ejecutada (gold_acciones_log)
  GET  /acciones                     consulta la bitácora de acciones
  GET  /resumen                      indicadores generales
  POST /powerbi/exportar             actualiza los CSV de Power BI desde la capa Gold

Uso:
  python -m src.api                  (o: uvicorn src.api:app --reload)
  Documentación interactiva (Swagger): http://127.0.0.1:8000/docs
"""
import sqlite3
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src import config
from src.db import crear_tabla_acciones
from src.exportar_powerbi import exportar as exportar_powerbi_csv

app = FastAPI(
    title="NovaBank - API de hiperpersonalización",
    description=(
        "MVP del servicio de **riesgo de abandono (churn)** de NovaBank. "
        "Devuelve la probabilidad de abandono de cada cliente, su nivel de riesgo y la "
        "**acción de retención recomendada**, y registra las acciones ejecutadas por el "
        "robot de UiPath."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Conexión a la base (se puede reemplazar en las pruebas)
# ---------------------------------------------------------------------------
def obtener_db():
    con = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def existe_tabla(con, tabla):
    fila = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabla,)).fetchone()
    return fila is not None


def exigir_predicciones(con):
    if not existe_tabla(con, "gold_predicciones"):
        raise HTTPException(status_code=503,
                            detail="No hay predicciones. Ejecute primero: python run_pipeline.py")


# ---------------------------------------------------------------------------
# Esquemas de respuesta (aparecen en Swagger)
# ---------------------------------------------------------------------------
class Recomendacion(BaseModel):
    cliente_id: str
    nombre: str
    segmento: str
    departamento: str
    prob_abandono: float = Field(description="Probabilidad de abandono en los próximos 90 días (0 a 1)")
    nivel_riesgo: str = Field(description="Alto (>= 0.45), Medio (0.20 - 0.45) o Bajo (< 0.20)")
    prediccion_abandono: int = Field(description="1 = el modelo predice que abandona")
    accion: str
    canal_contacto: str
    motivo: str
    prioridad: int = Field(description="1 = urgente, 2 = media, 3 = sin acción")
    modelo: str
    fecha_prediccion: str


class ClienteRiesgo(BaseModel):
    cliente_id: str
    nombre: str
    segmento: str
    prob_abandono: float
    nivel_riesgo: str
    accion: str
    canal_contacto: str
    motivo: str
    prioridad: int


class ListaClientesRiesgo(BaseModel):
    umbral: float
    total: int
    clientes: List[ClienteRiesgo]


class NuevaAccion(BaseModel):
    cliente_id: str = Field(examples=["C00010"])
    accion: Optional[str] = Field(None, description="Si no se envía, se usa la acción recomendada")
    canal_contacto: Optional[str] = Field(None, description="Si no se envía, se usa el canal recomendado")
    estado: str = Field("Ejecutada", examples=["Ejecutada"], description="Ejecutada, Fallida o Pendiente")
    ejecutado_por: str = Field("UiPath", examples=["UiPath"])
    detalle: Optional[str] = Field(None, examples=["Correo enviado al equipo de retención"])


class AccionRegistrada(BaseModel):
    id: int
    fecha_registro: str
    cliente_id: str
    nivel_riesgo: Optional[str]
    prob_abandono: Optional[float]
    accion: str
    canal_contacto: Optional[str]
    estado: str
    ejecutado_por: str
    detalle: Optional[str]


ESTADOS_VALIDOS = {"Ejecutada", "Fallida", "Pendiente"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/", tags=["General"], summary="Bienvenida")
def inicio():
    return {"servicio": "NovaBank - riesgo de abandono", "documentacion": "/docs", "estado": "/health"}


@app.get("/health", tags=["General"], summary="Estado de la API y de la base de datos")
def health(con=Depends(obtener_db)):
    if not existe_tabla(con, "gold_predicciones"):
        return {"estado": "sin_datos", "detalle": "Ejecute python run_pipeline.py"}
    fila = con.execute("SELECT COUNT(*) AS n, MAX(fecha_prediccion) AS f, MAX(modelo) AS m "
                       "FROM gold_predicciones").fetchone()
    return {"estado": "ok", "predicciones": fila["n"], "modelo": fila["m"], "fecha_prediccion": fila["f"]}


@app.get("/recomendacion/{cliente_id}", response_model=Recomendacion, tags=["Predicciones"],
         summary="Predicción y acción recomendada de un cliente")
def recomendacion(cliente_id: str, con=Depends(obtener_db)):
    """Devuelve la probabilidad de abandono, el nivel de riesgo y la acción recomendada."""
    exigir_predicciones(con)
    fila = con.execute("SELECT * FROM gold_predicciones WHERE cliente_id = ?",
                       (cliente_id.strip().upper(),)).fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail=f"Cliente {cliente_id} no encontrado")
    return dict(fila)


@app.get("/clientes/alto-riesgo", response_model=ListaClientesRiesgo, tags=["Predicciones"],
         summary="Clientes a contactar (los usa el robot de UiPath)")
def clientes_alto_riesgo(
    umbral: float = Query(0.45, ge=0, le=1, description="Probabilidad mínima de abandono"),
    limite: int = Query(50, ge=1, le=1500, description="Máximo de clientes a devolver"),
    solo_pendientes: bool = Query(True, description="Excluir clientes que ya tienen una acción ejecutada"),
    con=Depends(obtener_db),
):
    """Clientes con probabilidad >= umbral, ordenados del más al menos riesgoso."""
    exigir_predicciones(con)
    crear_tabla_acciones(con)
    sql = """SELECT cliente_id, nombre, segmento, prob_abandono, nivel_riesgo, accion,
                    canal_contacto, motivo, prioridad
             FROM gold_predicciones p
             WHERE prob_abandono >= ?"""
    if solo_pendientes:
        sql += """ AND NOT EXISTS (SELECT 1 FROM gold_acciones_log a
                                   WHERE a.cliente_id = p.cliente_id AND a.estado = 'Ejecutada')"""
    sql += " ORDER BY prob_abandono DESC LIMIT ?"
    filas = [dict(f) for f in con.execute(sql, (umbral, limite)).fetchall()]
    return {"umbral": umbral, "total": len(filas), "clientes": filas}


@app.post("/acciones", response_model=AccionRegistrada, status_code=201, tags=["Acciones"],
          summary="Registrar una acción ejecutada")
def registrar_accion(nueva: NuevaAccion, con=Depends(obtener_db)):
    """Guarda en gold_acciones_log la acción que se ejecutó sobre un cliente."""
    exigir_predicciones(con)
    if nueva.estado not in ESTADOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Estado no válido. Use uno de: {sorted(ESTADOS_VALIDOS)}")
    cliente_id = nueva.cliente_id.strip().upper()
    pred = con.execute("SELECT nivel_riesgo, prob_abandono, accion, canal_contacto "
                       "FROM gold_predicciones WHERE cliente_id = ?", (cliente_id,)).fetchone()
    if pred is None:
        raise HTTPException(status_code=404, detail=f"Cliente {cliente_id} no encontrado")

    crear_tabla_acciones(con)
    registro = {
        "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        "cliente_id": cliente_id,
        "nivel_riesgo": pred["nivel_riesgo"],
        "prob_abandono": pred["prob_abandono"],
        "accion": nueva.accion or pred["accion"],
        "canal_contacto": nueva.canal_contacto or pred["canal_contacto"],
        "estado": nueva.estado,
        "ejecutado_por": nueva.ejecutado_por,
        "detalle": nueva.detalle,
    }
    cursor = con.execute(
        f"INSERT INTO gold_acciones_log ({', '.join(registro)}) VALUES ({', '.join('?' * len(registro))})",
        tuple(registro.values()))
    con.commit()
    return {"id": cursor.lastrowid, **registro}


@app.get("/acciones", response_model=List[AccionRegistrada], tags=["Acciones"],
         summary="Consultar la bitácora de acciones")
def listar_acciones(limite: int = Query(100, ge=1, le=5000), con=Depends(obtener_db)):
    crear_tabla_acciones(con)
    filas = con.execute("SELECT * FROM gold_acciones_log ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    return [dict(f) for f in filas]


@app.get("/resumen", tags=["Predicciones"], summary="Indicadores generales")
def resumen(con=Depends(obtener_db)):
    """Indicadores que usa el robot para el correo resumen."""
    exigir_predicciones(con)
    crear_tabla_acciones(con)
    total = con.execute("SELECT COUNT(*) FROM gold_predicciones").fetchone()[0]
    niveles = {f["nivel_riesgo"]: {"clientes": f["n"], "saldo_total": round(f["saldo"], 2)}
               for f in con.execute("SELECT nivel_riesgo, COUNT(*) AS n, SUM(saldo_promedio) AS saldo "
                                    "FROM gold_predicciones GROUP BY nivel_riesgo")}
    ejecutadas = con.execute("SELECT COUNT(DISTINCT cliente_id) FROM gold_acciones_log "
                             "WHERE estado = 'Ejecutada'").fetchone()[0]
    alto = niveles.get("Alto", {"clientes": 0, "saldo_total": 0})
    return {
        "total_clientes": total,
        "por_nivel": niveles,
        "pct_alto_riesgo": round(alto["clientes"] / total, 4) if total else 0,
        "saldo_en_riesgo_alto": alto["saldo_total"],
        "clientes_con_accion_ejecutada": ejecutadas,
    }


@app.post("/powerbi/exportar", tags=["Power BI"], summary="Actualizar los CSV del tablero de Power BI")
def exportar_powerbi():
    """
    Exporta la capa Gold (predicciones, acciones del robot, actividad mensual y métricas
    del modelo) a powerbi/datos/. Después basta con "Actualizar" en Power BI.
    """
    try:
        archivos = exportar_powerbi_csv()
    except Exception as error:  # se informa el problema al robot
        raise HTTPException(status_code=500, detail=f"No se pudo exportar: {error}")
    return {"estado": "ok", "carpeta": "powerbi/datos", "archivos": archivos,
            "fecha": datetime.now().isoformat(timespec="seconds")}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000)
