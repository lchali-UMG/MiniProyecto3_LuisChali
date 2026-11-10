"""
Reporte HTML propio para las pruebas (sin JavaScript, se ve en cualquier navegador).

Se genera solo al terminar pytest en reports/:
  pytest -m ingesta   -> reports/pruebas_ingesta.html
  pytest -m unitaria  -> reports/pruebas_unitarias.html
  pytest              -> reports/pruebas_todas.html
"""
import html
import platform
import sys
from datetime import datetime

from src import config

ESTILO = """
body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#1f2933;background:#fff}
h1{margin:0 0 4px;font-size:24px;color:#1f4e79}
.sub{color:#52606d;margin-bottom:20px;font-size:13px}
.tarjetas{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}
.tarjeta{border:1px solid #d9e2ec;border-radius:8px;padding:12px 18px;min-width:120px}
.tarjeta b{display:block;font-size:26px}
.tarjeta span{font-size:12px;color:#52606d;text-transform:uppercase}
.ok b{color:#2f855a}.mal b{color:#c53030}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#1f4e79;color:#fff;text-align:left;padding:8px}
td{border-bottom:1px solid #e4e7eb;padding:7px 8px;vertical-align:top}
tr:nth-child(even) td{background:#f7f9fb}
.capa{font-weight:600}
.passed{color:#2f855a;font-weight:700}.failed,.error{color:#c53030;font-weight:700}.skipped{color:#b7791f;font-weight:700}
pre{white-space:pre-wrap;color:#c53030;margin:6px 0 0;font-size:12px}
"""

ETIQUETA = {"passed": "PASÓ", "failed": "FALLÓ", "error": "ERROR", "skipped": "OMITIDA"}


def capa_de(nombre):
    """La capa sale del nombre: test_<capa>_... (ej. test_gold_sin_nulos -> Gold)."""
    partes = nombre.split("_")
    capa = partes[1] if len(partes) > 1 else ""
    return capa.capitalize() if capa in {"bronze", "silver", "gold", "control"} else "Unitaria"


def nombre_archivo(markexpr):
    if markexpr == "ingesta":
        return "pruebas_ingesta.html"
    if markexpr == "unitaria":
        return "pruebas_unitarias.html"
    return "pruebas_todas.html"


def escribir_reporte(resultados, markexpr, segundos):
    total = len(resultados)
    pasaron = sum(r["estado"] == "passed" for r in resultados)
    fallaron = total - pasaron

    filas = []
    for i, r in enumerate(resultados, 1):
        error = f"<pre>{html.escape(r['error'])}</pre>" if r["error"] else ""
        filas.append(
            f"<tr><td>{i}</td><td class='capa'>{r['capa']}</td>"
            f"<td><code>{html.escape(r['nombre'])}</code></td>"
            f"<td>{html.escape(r['parametro'])}</td>"
            f"<td>{html.escape(r['descripcion'])}{error}</td>"
            f"<td class='{r['estado']}'>{ETIQUETA.get(r['estado'], r['estado'])}</td>"
            f"<td>{r['duracion'] * 1000:.0f} ms</td></tr>"
        )

    titulo = {"ingesta": "Pruebas de ingesta", "unitaria": "Pruebas unitarias"}.get(markexpr, "Pruebas")
    contenido = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>{titulo} - MVP NovaBank</title><style>{ESTILO}</style></head><body>
<h1>{titulo} - MVP NovaBank (riesgo de abandono)</h1>
<div class="sub">Generado el {datetime.now():%d/%m/%Y %H:%M:%S} &middot;
Python {platform.python_version()} &middot; {platform.system()} {platform.release()} &middot;
Base: {html.escape(config.DB_PATH.name)}</div>
<div class="tarjetas">
  <div class="tarjeta"><b>{total}</b><span>Pruebas</span></div>
  <div class="tarjeta ok"><b>{pasaron}</b><span>Pasaron</span></div>
  <div class="tarjeta {'mal' if fallaron else 'ok'}"><b>{fallaron}</b><span>Fallaron</span></div>
  <div class="tarjeta"><b>{segundos:.2f} s</b><span>Duración</span></div>
</div>
<table><tr><th>#</th><th>Capa</th><th>Prueba</th><th>Parámetro</th><th>Qué comprueba</th><th>Resultado</th><th>Tiempo</th></tr>
{''.join(filas)}
</table></body></html>"""

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = config.REPORTS_DIR / nombre_archivo(markexpr)
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def resultado_desde_reporte(item, rep):
    """Convierte el resultado de pytest de una prueba en un diccionario."""
    nombre = item.originalname if hasattr(item, "originalname") else item.name
    parametro = item.callspec.id if hasattr(item, "callspec") else ""
    doc = (item.function.__doc__ or "").strip().splitlines()
    estado = rep.outcome if rep.when == "call" else ("error" if rep.failed else rep.outcome)
    error = ""
    if rep.failed:
        error = str(rep.longrepr.reprcrash.message) if hasattr(rep.longrepr, "reprcrash") else str(rep.longrepr)
    return {
        "nombre": nombre, "parametro": parametro, "capa": capa_de(nombre),
        "descripcion": doc[0] if doc else "", "estado": estado,
        "duracion": rep.duration, "error": error,
    }


if __name__ == "__main__":
    sys.exit("Este módulo lo usa pytest automáticamente (ver tests/conftest.py).")
