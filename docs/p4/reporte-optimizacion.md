# P4-08 — Reporte de recursos antes/después (p50/p95, tamaño)

**Issue:** [#8](https://github.com/sanchezesteban/MLOPS_p4/issues/8) · **Responsable:** Uriel (@urielpinag)
**Ámbito:** rúbrica 3.2, 3.3 — justificar la decisión de optimización.

> **Estado:** herramienta y método listos; los tiempos de la Pi llegan con el benchmark real (issue #11). `reports/p4/resources.json` sale por ahora con la parte de **tamaño** y `latency = null`.

## Método (recalculable)

- **Percentil:** interpolación lineal de `numpy.percentile(..., method="linear")`. Se reportan **p50 y p95** por variante.
- **Reducción de tamaño:** `100 * (tamaño_fp32 - tamaño_int8) / tamaño_fp32`, con los bytes de `reports/p4/conversion_log.json`.
- **Aceleración:** solo se marca como `significant` si la diferencia entre las medianas **supera la variabilidad combinada** (suma de las desviaciones estándar). Si no, se reporta como dentro del ruido.

## Entrada del benchmark (issue #11)

CSV con dos columnas, una fila por medición:

```csv
variant,latency_ms
fp32,412.7
fp32,398.1
int8,180.4
int8,176.9
```

- `variant`: `fp32` o `int8`.
- `latency_ms`: preprocesamiento + inferencia, **sin** envío (igual que el contrato del evento).

## Cómo se corre

```console
$ cd app
$ uv run --locked --no-build python edge/resource_report.py \
    --conversion-log ../reports/p4/conversion_log.json \
    --benchmark ../reports/p4/benchmark.csv \
    --output ../reports/p4/resources.json
```

Sin `--benchmark` genera el reporte parcial (tamaño real, latencia pendiente).

## Resultados

### Tamaño (real)

| Artefacto | Bytes | Reducción |
|---|---|---|
| ONNX FP32 | 45 224 191 | — |
| ONNX INT8 | 11 430 716 | **74.72 %** |

### Calidad (issue #6)

Caída de accuracy INT8 vs. original: **0.00 pp** (meta ≤ 2 pp). La optimización no cambió ninguna predicción.

### Latencia (pendiente #11)

`p50`/`p95` de FP32 e INT8 y la aceleración se llenan cuando exista el CSV del benchmark de la Pi. `reports/p4/resources.json` quedará con `status: "completo"`.

## Intercambio recursos vs. calidad para la Zero 2 W

La Zero 2 W tiene **4 núcleos ARM Cortex-A53 y 512 MB de RAM**: el presupuesto de cómputo manda. La cuantización estática INT8 reduce el modelo a **~1/4 del tamaño** (74.72 % menos), lo que abarata la carga en memoria (crítico con 512 MB) y, en ARM, aprovecha rutas INT8 que suelen acelerar la inferencia. El costo en calidad medido es **nulo** en la validación del P3 (0.00 pp). La decisión, por tanto, es favorable mientras el benchmark (#11) no muestre una aceleración *dentro del ruido*: si INT8 no acelera, sigue ganando por memoria y tamaño; si acelera, mejor aún.

## Evidencia

- `reports/p4/resources.json` (parcial, tamaño real).
- `app/edge/resource_report.py` y `app/tests/test_resource_report.py` (7 pruebas: percentiles, reducción, significancia).
