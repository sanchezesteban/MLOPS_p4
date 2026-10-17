# P4-08 — Reporte de recursos antes/después (p50/p95, tamaño)

**Issue:** [#8](https://github.com/sanchezesteban/MLOPS_p4/issues/8) · **Responsable:** Uriel (@urielpinag)
**Ámbito:** rúbrica 3.2, 3.3 — justificar la decisión de optimización.

> **Estado: completo.** Con el benchmark real de la Pi (issue #11) `reports/p4/resources.json` sale con `status: "completo"`.

## Método (recalculable)

- **Percentil:** interpolación lineal de `numpy.percentile(..., method="linear")`. Se reportan **p50 y p95** por variante.
- **Reducción de tamaño:** `100 * (tamaño_fp32 - tamaño_int8) / tamaño_fp32`, con los bytes de `reports/p4/conversion_log.json`.
- **Aceleración:** solo se marca como `significant` si la diferencia entre las medianas **supera la variabilidad combinada** (suma de las desviaciones estándar). Si no, se reporta como dentro del ruido.
- **Calentamiento:** las filas con `warmup=true` se **identifican, excluyen y contabilizan** (`warmup_discarded`); cada variante exige **≥ 100 mediciones válidas**.

## Entrada del benchmark (issue #11)

**Un solo archivo** `reports/p4/benchmark.csv`, una fila por medición:

```csv
variant,repetition,warmup,latency_ms
fp32,1,true,520.3
fp32,2,true,515.8
int8,1,true,505.1
fp32,11,false,410.2
```

- `variant`: `fp32` o `int8`; `repetition`: numeración; `warmup`: `true` = calentamiento.
- `latency_ms`: preprocesamiento + inferencia, **sin** envío (igual que el contrato del evento).

Condiciones de la corrida (`reports/p4/benchmark_conditions.json`): 10 de calentamiento + 100 mediciones por variante sobre el recorte `validacion/000005_000004.jpg`, ONNX Runtime 1.31.0 en la Zero 2 W, temperatura 50.5 → 68.2 °C, RSS pico 118 MB.

## Cómo se corre

```console
$ cd app
$ uv run --locked --no-build python edge/resource_report.py \
    --conversion-log ../reports/p4/conversion_log.json \
    --benchmark ../reports/p4/benchmark.csv \
    --output ../reports/p4/resources.json
```

## Resultados

### Latencia en la Raspberry Pi Zero 2 W (real)

| Variante | n | p50 (ms) | p95 (ms) | mín | máx | σ |
|---|---|---|---|---|---|---|
| ONNX FP32 | 100 | **142.24** | **148.13** | 141.39 | 192.29 | 5.53 |
| ONNX INT8 | 100 | **70.18** | **71.62** | 69.88 | 73.76 | 0.67 |

Se descartaron 10 filas de calentamiento por variante (20 de 220).

**Condiciones equivalentes (criterio 3.1).** Ambas variantes se midieron en la misma Raspberry Pi
Zero 2 W, en la misma corrida, con la misma imagen de entrada (`000005_000004.jpg`, de validación),
el mismo preprocesamiento, el mismo runtime (onnxruntime 1.31.0, `CPUExecutionProvider`, hilos por
defecto) y el mismo tamaño de entrada (1×3×128×128). El original se mide como **ONNX FP32 exportado
de los mismos pesos del `best.pt`** (SHA `f759cde2…`): PyTorch no se instala en la Zero 2 W
(512 MB de RAM, sin necesidad para el despliegue), y el FP32 en ONNX da exactamente las mismas
predicciones que PyTorch en las 131 muestras de validación (`reports/p4/quality_predictions.csv`,
columnas `original_pred` y `fp32_pred`). Así la única variable entre las dos mediciones es la
cuantización. FP32 corrió primero; la temperatura subió de 50.5 °C a 68.2 °C durante la corrida, lo
que, si acaso, penaliza a la INT8 (medida después), no la favorece.

- **Aceleración INT8 vs. FP32:** ×**2.03** en p50 y ×**2.07** en p95 — `significant: true` (la diferencia de medianas, ~72 ms, supera la variabilidad combinada de 6.2 ms; no es ruido).
- Además de ir al doble de velocidad, la INT8 tiene **menos dispersión** (σ 0.67 ms vs 5.53 ms): las latencias son más predecibles, útil para el presupuesto de tiempo del recorrido.

### Tamaño

| Artefacto | Bytes | Reducción |
|---|---|---|
| ONNX FP32 | 45 224 191 | — |
| ONNX INT8 | 11 430 716 | **74.72 %** |

### Calidad (issue #6)

Caída de accuracy INT8 vs. original: **0.00 pp** (meta ≤ 2 pp) sobre la validación del P3 (131 recortes). La optimización no cambió ninguna predicción.

## Conclusión: intercambio recursos vs. calidad para la Zero 2 W

La Zero 2 W (4 núcleos Cortex-A53, 512 MB de RAM) es el cuello de botella del recorrido, y la cuantización INT8 es favorable en **las tres dimensiones medidas**:

1. **Velocidad:** ×2.03 (p50) / ×2.07 (p95) — con significancia estadística, no fruto del ruido.
2. **Tamaño:** −74.72 %, ~1/4 del modelo; menos presión de memoria y de disco en la microSD.
3. **Calidad:** 0.00 pp de caída; los 5 errores de la validación son del modelo del P3, no de la optimización.

Por lo tanto, el **INT8 es la variante a desplegar** en la Pi: no hay *trade-off* perceptible, solo ganancias. Evidencia cruda recalculable: `reports/p4/resources.json` (`status: "completo"`).

## Evidencia

- `reports/p4/resources.json` (completo).
- `reports/p4/benchmark.csv` + `reports/p4/benchmark_conditions.json` (frente dispositivo, #11).
- `app/edge/resource_report.py` y `app/tests/test_resource_report.py` (9 pruebas: percentiles, reducción, significancia, calentamiento y regla de 100 válidas).
