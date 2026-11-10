# Tablero Power BI — NovaBank: riesgo de abandono

El tablero lee los CSV de la capa Gold que se generan en `powerbi/datos/`:

| Cuándo se actualizan | Cómo |
|---|---|
| Al correr el pipeline | `python run_pipeline.py` (paso 7) |
| Cada vez que corre el robot de UiPath | Paso 4 del robot → `POST /powerbi/exportar` |
| Manualmente | `python -m src.exportar_powerbi` |

Después, en Power BI basta con **Inicio → Actualizar**.

| Archivo | Contenido |
|---|---|
| `clientes_predicciones.csv` | 1 fila por cliente: perfil, comportamiento, `prob_abandono`, `nivel_riesgo`, `accion`, `canal_contacto`, `motivo`, `prioridad`, `estado_contacto` (Contactado por el robot / Pendiente / No requiere acción) |
| `acciones_log.csv` | Acciones registradas por el robot (`tipo_gestion`: Urgente / Campaña) |
| `actividad_mensual.csv` | Transacciones por mes y nivel de riesgo (`trx_por_cliente`) |
| `metricas_modelo.csv` | AUC, F1, Precisión, Recall, Exactitud del modelo |
| `importancia_variables.csv` | Variables que más influyen en el abandono |

---

## 1. Cargar los datos (Power Query)

1. **Inicio → Transformar datos → Nuevo origen → Consulta en blanco.** Renombrarla `RutaDatos` y en el
   **Editor avanzado** pegar (cambiar la ruta si el repo está en otro lugar; debe terminar en `\`):

   ```
   "S:\UMG2024\Sexto Semestre\Programación para la Ciencia de Datos\MiniProyecto_03\MiniProyecto3_LuisChali\powerbi\datos\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
   ```

2. Crear una **consulta en blanco por tabla**, con el nombre indicado, y pegar su código en el **Editor avanzado**.
   Se usa la cultura `en-US` para que el punto decimal se lea bien.

**clientes_predicciones**
```
let
    Origen = Csv.Document(File.Contents(RutaDatos & "clientes_predicciones.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {
        {"edad", Int64.Type}, {"saldo_promedio", type number}, {"num_productos", Int64.Type},
        {"tendencia_actividad", type number}, {"quejas_no_resueltas", Int64.Type},
        {"prob_abandono", type number}, {"prediccion_abandono", Int64.Type}, {"prioridad", Int64.Type},
        {"abandono_real", Int64.Type}, {"ingreso_mensual", type number}, {"antiguedad_meses", Int64.Type},
        {"tiene_tarjeta_credito", Int64.Type}, {"tiene_prestamo", Int64.Type}, {"score_crediticio", Int64.Type},
        {"trx_12m", Int64.Type}, {"monto_12m", type number}, {"trx_ult_3m", Int64.Type},
        {"pct_digital", type number}, {"dias_sin_trx", Int64.Type}, {"consultas_12m", Int64.Type},
        {"quejas_12m", Int64.Type}, {"contactado", Int64.Type}, {"orden_riesgo", Int64.Type}
    }, "en-US")
in
    Tipos
```

**acciones_log**
```
let
    Origen = Csv.Document(File.Contents(RutaDatos & "acciones_log.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {
        {"id", Int64.Type}, {"prob_abandono", type number}, {"fecha_registro", type datetime}, {"fecha", type date}
    }, "en-US")
in
    Tipos
```

**actividad_mensual**
```
let
    Origen = Csv.Document(File.Contents(RutaDatos & "actividad_mensual.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {
        {"transacciones", Int64.Type}, {"monto", type number}, {"clientes_activos", Int64.Type},
        {"clientes_nivel", Int64.Type}, {"trx_por_cliente", type number}, {"fecha_mes", type date},
        {"orden_riesgo", Int64.Type}
    }, "en-US")
in
    Tipos
```

**metricas_modelo**
```
let
    Origen = Csv.Document(File.Contents(RutaDatos & "metricas_modelo.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {{"valor", type number}, {"orden", Int64.Type}, {"umbral", type number}}, "en-US")
in
    Tipos
```

**importancia_variables**
```
let
    Origen = Csv.Document(File.Contents(RutaDatos & "importancia_variables.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {{"importancia", type number}}, "en-US")
in
    Tipos
```

3. **Cerrar y aplicar.**

## 2. Modelo de datos

- Relación: `clientes_predicciones[cliente_id]` (1) → `acciones_log[cliente_id]` (*).
- En `clientes_predicciones`, seleccionar la columna `nivel_riesgo` → **Herramientas de columna → Ordenar por
  columna → `orden_riesgo`** (para que el orden sea Alto, Medio, Bajo). Lo mismo en `actividad_mensual`.
- Formato: `prob_abandono` como **Porcentaje** (1 decimal); `saldo_promedio` como moneda **Q**.
- **Vista → Temas → Buscar temas** → `powerbi/tema_novabank.json`.

## 3. Medidas DAX

Crear una tabla vacía para las medidas (**Inicio → Especificar datos** → nombre `Medidas` → Cargar) y agregar:

```DAX
Clientes = COUNTROWS ( clientes_predicciones )

Clientes riesgo alto =
CALCULATE ( [Clientes], clientes_predicciones[nivel_riesgo] = "Alto" )

% Clientes riesgo alto = DIVIDE ( [Clientes riesgo alto], [Clientes] )

Saldo en riesgo alto =
CALCULATE ( SUM ( clientes_predicciones[saldo_promedio] ), clientes_predicciones[nivel_riesgo] = "Alto" )

Abandonos esperados = SUM ( clientes_predicciones[prob_abandono] )

Contactados por el robot =
CALCULATE ( [Clientes], clientes_predicciones[contactado] = 1 )

% Cobertura riesgo alto =
DIVIDE (
    CALCULATE ( [Clientes], clientes_predicciones[nivel_riesgo] = "Alto", clientes_predicciones[contactado] = 1 ),
    [Clientes riesgo alto]
)

Pendientes riesgo alto =
[Clientes riesgo alto]
    - CALCULATE ( [Clientes], clientes_predicciones[nivel_riesgo] = "Alto", clientes_predicciones[contactado] = 1 )

Prob. media de abandono = AVERAGE ( clientes_predicciones[prob_abandono] )

Abandono real = AVERAGE ( clientes_predicciones[abandono_real] )

AUC del modelo =
CALCULATE ( MAX ( metricas_modelo[valor] ), metricas_modelo[metrica] = "AUC" )

Acciones registradas = COUNTROWS ( acciones_log )
```

Formatos: los `%` como porcentaje con 1 decimal; `Saldo en riesgo alto` como moneda Q sin decimales;
`AUC del modelo` con 3 decimales; `Abandonos esperados` sin decimales.

## 4. Diseño del tablero (historia en 3 actos)

### Página 1 — "¿Quiénes se van y qué hacemos?"

**Título (cuadro de texto):** *NovaBank — 188 clientes en riesgo alto de abandono: el robot ya los está contactando*

**Fila de indicadores (4 tarjetas):**

| Tarjeta | Medida | Qué cuenta |
|---|---|---|
| 1 | `% Clientes riesgo alto` | El tamaño del problema (~12.5 %) |
| 2 | `Saldo en riesgo alto` | Cuánto dinero está en juego (~Q1.3 M) |
| 3 | `Abandonos esperados` | Cuántos clientes se perderían sin actuar |
| 4 | `% Cobertura riesgo alto` | Cuánto del riesgo ya atendió el robot (sube cada vez que corre) |

**Visuales:**

1. **Gráfico de anillos** — Leyenda: `nivel_riesgo`; Valores: `Clientes`. Colores: Alto rojo, Medio naranja, Bajo verde.
2. **Gráfico de líneas** (tabla `actividad_mensual`) — Eje X: `fecha_mes`; Eje Y: `trx_por_cliente`; Leyenda: `nivel_riesgo`.
   Título: *"Los clientes en riesgo alto reducen su actividad en los últimos 3 meses"*.
3. **Gráfico de barras horizontales** — Eje Y: `accion`; Eje X: `Clientes`; filtro del visual: `prioridad` < 3.
   Título: *"Acción de retención recomendada"*.
4. **Tabla** — `cliente_id`, `nombre`, `segmento`, `prob_abandono`, `accion`, `canal_contacto`, `estado_contacto`;
   filtro: `nivel_riesgo` = Alto; ordenar por `prob_abandono` descendente. Formato condicional → color de fondo
   en `prob_abandono` (escala verde → rojo) y en `estado_contacto` (verde = Contactado, naranja = Pendiente).
5. **Segmentaciones:** `segmento`, `departamento`, `estado_contacto`.

### Página 2 — "¿Qué tan confiable es el modelo?"

1. **Tarjeta:** `AUC del modelo` (0.822) con el texto "Regresión Logística — 1 = perfecto, 0.5 = azar".
2. **Tabla** (`metricas_modelo`): `metrica`, `valor` (ordenar por `orden`).
3. **Barras horizontales** (`importancia_variables`): `variable` vs `importancia`.
   Título: *"Lo que más anticipa el abandono: caída de transacciones y quejas sin resolver"*.
4. **Gráfico de columnas agrupadas** — Eje X: `nivel_riesgo`; Valores: `Prob. media de abandono` y `Abandono real`.
   Título: *"Las probabilidades están calibradas: lo que predice el modelo coincide con lo que pasó"*.

### Página 3 (opcional) — "Seguimiento del robot"

- Tarjeta `Acciones registradas`; columnas por `tipo_gestion` (Urgente / Campaña); tabla de `acciones_log`
  (`fecha_registro`, `cliente_id`, `accion`, `canal_contacto`, `detalle`).

## 5. Guardar y demo

- Guardar como `powerbi/NovaBank_Retencion.pbix` y exportar también a PDF (**Archivo → Exportar → PDF**) para el informe.
- En la demo: correr el robot → en Power BI **Actualizar** → la tarjeta `% Cobertura riesgo alto` sube y la tabla
  muestra los clientes "Contactado por el robot".
