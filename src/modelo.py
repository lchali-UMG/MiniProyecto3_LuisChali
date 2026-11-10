"""
Parte 4 - Entrenamiento y evaluación del modelo de abandono (churn).

Pasos:
  1. Lee gold_features_cliente.
  2. Separa 75 % entrenamiento / 25 % prueba (estratificado, semilla fija).
  3. Entrena 2 modelos: Regresión Logística y Random Forest.
  4. Compara con validación cruzada (AUC) y elige el mejor.
  5. Elige el umbral de decisión que maximiza el F1 (también con validación
     cruzada, solo con datos de entrenamiento).
  6. Evalúa el mejor en el conjunto de prueba: AUC, F1, precisión, recall,
     exactitud y matriz de confusión.
  7. Guarda el modelo (models/), las métricas (reports/metricas_modelo.json)
     y las gráficas (reports/figuras/).

Uso:  python -m src.modelo
"""
import json
from datetime import datetime

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import (StratifiedKFold, cross_val_predict, cross_val_score,
                                     train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src import config
from src.db import conectar, leer_tabla

OBJETIVO = "abandono"
VARIABLES_NUMERICAS = [
    "edad", "ingreso_mensual", "antiguedad_meses", "num_productos",
    "tiene_tarjeta_credito", "tiene_prestamo", "saldo_promedio", "score_crediticio",
    "trx_12m", "monto_12m", "trx_ult_3m", "pct_digital", "tipos_distintos",
    "tendencia_actividad", "dias_sin_trx", "consultas_12m", "quejas_12m",
    "quejas_no_resueltas",
]
VARIABLES_CATEGORICAS = ["segmento", "canal_preferido", "genero"]
VARIABLES = VARIABLES_NUMERICAS + VARIABLES_CATEGORICAS
UMBRALES_CANDIDATOS = np.round(np.arange(0.10, 0.65, 0.05), 2)
ARCHIVO_MODELO = config.MODELS_DIR / "modelo_abandono.joblib"
ARCHIVO_METRICAS = config.REPORTS_DIR / "metricas_modelo.json"


def crear_modelos():
    """Los dos candidatos, cada uno con su preprocesamiento."""
    prep_lineal = ColumnTransformer([
        ("num", StandardScaler(), VARIABLES_NUMERICAS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), VARIABLES_CATEGORICAS),
    ])
    prep_arbol = ColumnTransformer([
        ("num", "passthrough", VARIABLES_NUMERICAS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), VARIABLES_CATEGORICAS),
    ])
    # Sin "class_weight": así la probabilidad queda calibrada (si el modelo dice
    # 30 %, abandona ~30 % de esos clientes). El desbalance (~18 % abandona) se
    # maneja eligiendo un umbral de decisión menor a 0.5.
    return {
        "Regresión Logística": Pipeline([
            ("prep", prep_lineal),
            ("modelo", LogisticRegression(max_iter=2000)),
        ]),
        "Random Forest": Pipeline([
            ("prep", prep_arbol),
            ("modelo", RandomForestClassifier(n_estimators=300, min_samples_leaf=5,
                                              random_state=config.SEMILLA, n_jobs=-1)),
        ]),
    }


def elegir_umbral(modelo, X, y, cv):
    """Umbral que maximiza el F1 usando predicciones de validación cruzada."""
    prob = cross_val_predict(modelo, X, y, cv=cv, method="predict_proba")[:, 1]
    f1s = {float(u): f1_score(y, (prob >= u).astype(int)) for u in UMBRALES_CANDIDATOS}
    return max(f1s, key=f1s.get)


def calcular_metricas(y_real, prob, umbral):
    pred = (prob >= umbral).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_real, pred).ravel()
    return {
        "auc": round(float(roc_auc_score(y_real, prob)), 4),
        "f1": round(float(f1_score(y_real, pred)), 4),
        "precision": round(float(precision_score(y_real, pred)), 4),
        "recall": round(float(recall_score(y_real, pred)), 4),
        "exactitud": round(float(accuracy_score(y_real, pred)), 4),
        "matriz_confusion": {"vn": int(tn), "fp": int(fp), "fn": int(fn), "vp": int(tp)},
    }


def graficar(resultados, mejor, y_prueba, importancias, umbral):
    config.FIGURAS_DIR.mkdir(parents=True, exist_ok=True)

    # Curvas ROC
    fig, ax = plt.subplots(figsize=(6.5, 6))
    for nombre, r in resultados.items():
        fpr, tpr, _ = roc_curve(y_prueba, r["prob_prueba"])
        ax.plot(fpr, tpr, lw=2, label=f"{nombre} (AUC = {r['prueba']['auc']:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="grey", label="Azar (AUC = 0.5)")
    ax.set_xlabel("Tasa de falsos positivos")
    ax.set_ylabel("Tasa de verdaderos positivos (recall)")
    ax.set_title("Curva ROC - conjunto de prueba")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(config.FIGURAS_DIR / "03_curva_roc.png", dpi=120)
    plt.close(fig)

    # Matriz de confusión del mejor modelo
    m = resultados[mejor]["prueba"]["matriz_confusion"]
    matriz = np.array([[m["vn"], m["fp"]], [m["fn"], m["vp"]]])
    fig, ax = plt.subplots(figsize=(5.5, 4.8))
    ax.imshow(matriz, cmap="Blues")
    etiquetas = [["Verdadero negativo", "Falso positivo"], ["Falso negativo", "Verdadero positivo"]]
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{matriz[i, j]}\n{etiquetas[i][j]}", ha="center", va="center",
                    color="white" if matriz[i, j] > matriz.max() / 2 else "black", fontsize=11)
    ax.set_xticks([0, 1], ["Se queda", "Abandona"])
    ax.set_yticks([0, 1], ["Se queda", "Abandona"])
    ax.set_xlabel("Predicción del modelo")
    ax.set_ylabel("Valor real")
    ax.set_title(f"Matriz de confusión - {mejor} (umbral {umbral:.2f})")
    fig.tight_layout()
    fig.savefig(config.FIGURAS_DIR / "04_matriz_confusion.png", dpi=120)
    plt.close(fig)

    # Variables más importantes
    top = importancias.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.barh(top.index, top.values, color="#1f4e79")
    ax.set_xlabel("Pérdida de AUC al desordenar la variable")
    ax.set_title(f"Variables más importantes - {mejor}")
    fig.tight_layout()
    fig.savefig(config.FIGURAS_DIR / "05_importancia_variables.png", dpi=120)
    plt.close(fig)


def entrenar():
    con = conectar()
    datos = leer_tabla(con, "gold_features_cliente")
    con.close()

    X, y = datos[VARIABLES], datos[OBJETIVO]
    X_ent, X_pru, y_ent, y_pru = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=config.SEMILLA)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.SEMILLA)
    resultados = {}
    for nombre, modelo in crear_modelos().items():
        auc_cv = cross_val_score(modelo, X_ent, y_ent, cv=cv, scoring="roc_auc")
        umbral = elegir_umbral(modelo, X_ent, y_ent, cv)
        modelo.fit(X_ent, y_ent)
        prob = modelo.predict_proba(X_pru)[:, 1]
        resultados[nombre] = {
            "modelo": modelo,
            "umbral": umbral,
            "auc_cv_media": round(float(auc_cv.mean()), 4),
            "auc_cv_desv": round(float(auc_cv.std()), 4),
            "prueba": calcular_metricas(y_pru, prob, umbral),
            "prob_prueba": prob,
        }
        print(f"  {nombre:<20} AUC validación cruzada = {auc_cv.mean():.3f} ± {auc_cv.std():.3f}"
              f" | AUC prueba = {resultados[nombre]['prueba']['auc']:.3f}")

    # El mejor se elige por validación cruzada (no por el conjunto de prueba)
    mejor = max(resultados, key=lambda n: resultados[n]["auc_cv_media"])
    modelo = resultados[mejor]["modelo"]
    umbral = resultados[mejor]["umbral"]

    imp = permutation_importance(modelo, X_pru, y_pru, scoring="roc_auc", n_repeats=10,
                                 random_state=config.SEMILLA, n_jobs=-1)
    importancias = pd.Series(imp.importances_mean, index=VARIABLES).sort_values(ascending=False)

    graficar(resultados, mejor, y_pru, importancias, umbral)

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modelo": modelo, "nombre": mejor, "variables": VARIABLES, "umbral": umbral,
                 "ids_entrenamiento": datos.loc[X_ent.index, "cliente_id"].tolist()}, ARCHIVO_MODELO)

    metricas = {
        "fecha_entrenamiento": datetime.now().isoformat(timespec="seconds"),
        "modelo_elegido": mejor,
        "umbral": umbral,
        "registros": {"entrenamiento": len(X_ent), "prueba": len(X_pru),
                      "tasa_abandono": round(float(y.mean()), 4)},
        "comparacion": {n: {"auc_cv_media": r["auc_cv_media"], "auc_cv_desv": r["auc_cv_desv"],
                            "umbral": r["umbral"], "prueba": r["prueba"]}
                        for n, r in resultados.items()},
        "importancia_variables": {k: round(float(v), 4) for k, v in importancias.head(10).items()},
    }
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVO_METRICAS.write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")
    return metricas


def main():
    print("MODELO - entrenamiento y evaluación")
    m = entrenar()
    p = m["comparacion"][m["modelo_elegido"]]["prueba"]
    print(f"\n  Modelo elegido: {m['modelo_elegido']}")
    print(f"  Conjunto de prueba ({m['registros']['prueba']} clientes, umbral {m['umbral']}):")
    print(f"    AUC = {p['auc']:.3f} | F1 = {p['f1']:.3f} | Precisión = {p['precision']:.3f} "
          f"| Recall = {p['recall']:.3f} | Exactitud = {p['exactitud']:.3f}")
    print(f"  Variables más importantes: {', '.join(list(m['importancia_variables'])[:5])}")
    print(f"  Modelo: {ARCHIVO_MODELO}\n  Métricas: {ARCHIVO_METRICAS}")


if __name__ == "__main__":
    main()
