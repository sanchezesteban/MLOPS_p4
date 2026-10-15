# P4-06 — Comparación de calidad: original vs. optimizado

**Issue:** [#6](https://github.com/sanchezesteban/MLOPS_p4/issues/6) · **Responsable:** Uriel (@urielpinag)
**Ámbito:** rúbrica 1.3 — evaluar ambos modelos sobre la misma validación del Proyecto 3.

## Resumen

Los tres modelos se evaluaron sobre el **split `val`** del manifiesto `v0.1.1` (131 recortes), con la misma entrada y el mismo preprocesamiento:

| Modelo | Accuracy | F1 macro |
|---|---|---|
| `original` (PyTorch `best.pt`, r02) | `0.9618320610687023` | `0.9618231625575566` |
| `fp32` (ONNX FP32) | `0.9618320610687023` | `0.9618231625575566` |
| `optimized` (ONNX INT8) | `0.9618320610687023` | `0.9618231625575566` |

**Caída de accuracy INT8 vs. original: 0.00 pp** (meta ≤ 2 pp ✅). La cuantización **no** cambió ninguna predicción.

## Métricas por clase

| Clase | Precisión | Recall | F1 | Soporte |
|---|---|---|---|---|
| cat | 0.970 | 0.955 | 0.962 | 67 |
| dog | 0.954 | 0.969 | 0.961 | 64 |

Idénticas para los tres modelos.

## Matriz de confusión (filas = real, columnas = predicho)

|  | pred cat | pred dog |
|---|---|---|
| **real cat** | 64 | 3 |
| **real dog** | 2 | 62 |

## Análisis de errores

- **Errores de la cuantización:** `0` discrepancias entre PyTorch y ONNX INT8 (`error_analysis.disagreements = []`). El export a FP32 y la cuantización INT8 tampoco introducen diferencias respecto al modelo PyTorch.
- **Errores propios del modelo (compartidos por los tres):** 5 de 131 muestras (3.8 %). Clases afectadas: **cat** (3 gatos clasificados como *dog*) y **dog** (2 perros clasificados como *cat*). Son límites de decisión del modelo del P3, no de la optimización.

Los 5 recortes mal clasificados (de `reports/p4/quality_predictions.csv`):

| `crop_id` | Real | Predicho |
|---|---|---|
| `000135_000153` | cat | dog |
| `000526_000521` | cat | dog |
| `000633_000627` | cat | dog |
| `000289_000331` | dog | cat |
| `000476_000467` | dog | cat |
- Conclusión: en esta validación, **el intercambio calidad ↔ recursos es favorable** — la INT8 pesa 74.7 % menos sin perder ni una muestra (el lado de recursos se mide en #8).

## Evidencia

- `reports/p4/quality_predictions.csv` — una fila por muestra: `crop_id`, `true_class`, `original_pred`, `optimized_pred` (+ `fp32_pred`).
- `reports/p4/quality_metrics.json` — accuracy, F1 macro, métricas por clase, matriz de confusión, caída en pp y análisis de errores.

## Cómo reproducirlo

```console
$ cd app
$ uv run --locked --no-build --group ml python edge/compare_quality.py \
    --checkpoint ../models/p3/r02/best.pt \
    --fp32 ../models/p3/r02/onnx/model_fp32.onnx \
    --int8 ../models/p3/r02/onnx/model_int8.onnx \
    --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
    --crops-root ../data/derived/crops \
    --report-dir ../reports/p4
```

Solo usa el split `val`; `test` queda reservado (custodia del P3).
