# Diagramas del MVP

Cada diagrama tiene su **archivo fuente** (`.mmd`, formato Mermaid) y su imagen (`.png`).

| Archivo | Diagrama |
|---|---|
| `01_c4_nivel1_contexto` | C4 nivel 1: contexto del sistema |
| `02_c4_nivel2_contenedores` | C4 nivel 2: contenedores (todo el sistema) |
| `03_pipeline_end_to_end` | Fuentes → Ingesta → Almacenamiento crudo → ETL → Servidor/MLOps → Consumo |
| `04_zonas_almacenamiento` | Zonas de datos: estructurados, semi-estructurados, no estructurados y no tradicionales |
| `05_flujo_robot_uipath` | Secuencia del robot: disparador → predicciones → regla → acción |
| `06_modelo_datos_gold` | Modelo de datos de las capas Silver y Gold |

## Cómo editar

- **Mermaid Live:** pegar el contenido del `.mmd` en <https://mermaid.live>.
- **draw.io:** *Organizar → Insertar → Avanzado → Mermaid* y pegar el contenido.
- **Regenerar las imágenes:** `mmdc -i archivo.mmd -o archivo.png -b white -s 2`
