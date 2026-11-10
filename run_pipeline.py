"""
Pipeline completo del MVP de NovaBank (de principio a fin).

  1. Datos sintéticos  (solo si no existen, o con --regenerar)
  2. Validación de datos
  3. Ingesta  -> Bronze
  4. Limpieza -> Silver
  5. Variables por cliente -> Gold
  6. Entrenamiento y evaluación del modelo
  7. Predicción + acción recomendada -> Gold (gold_predicciones)

Uso:
  python run_pipeline.py              # usa los CSV existentes
  python run_pipeline.py --regenerar  # vuelve a generar los datos sintéticos
"""
import argparse
import time

from src import config, generar_datos, ingesta, modelo, predecir, transformar, validar_datos


def paso(numero, titulo):
    print(f"\n{'=' * 70}\n[{numero}] {titulo}\n{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(description="Pipeline MVP NovaBank")
    parser.add_argument("--regenerar", action="store_true", help="volver a generar los datos sintéticos")
    args = parser.parse_args()
    inicio = time.time()

    faltan = any(not (config.DATA_RAW / a).exists() for a in config.FUENTES.values())
    if args.regenerar or faltan:
        paso(1, "Generación de datos sintéticos")
        generar_datos.main()
    else:
        paso(1, "Datos sintéticos: se usan los CSV existentes en data/raw/")

    paso(2, "Validación de datos")
    validar_datos.main()

    paso(3, "Ingesta -> capa BRONZE")
    ingesta.main()

    paso(4, "Limpieza -> capa SILVER  |  Variables -> capa GOLD")
    transformar.main()

    paso(5, "Modelo de abandono: entrenamiento y evaluación")
    modelo.main()

    paso(6, "Predicción y acción recomendada -> GOLD")
    predecir.main()

    print(f"\nPipeline terminado en {time.time() - inicio:.1f} s  ->  {config.DB_PATH}")


if __name__ == "__main__":
    main()
