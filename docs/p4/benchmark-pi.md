# P4-11 — Benchmark en la Pi: FP32 vs. INT8

**Issue:** [#11](https://github.com/sanchezesteban/MLOPS_p4/issues/11) · **Responsable:** Juan Pablo (@jpdelmuro)
**Ámbito:** rúbrica 3.1, 3.2.

## Formato del CSV

El ticket original pedía dos archivos (`latency_fp32.csv`, `latency_int8.csv`); se acordó con Uriel
(corrección de revisión en #39, P4-08) usar **un solo archivo**
[`reports/p4/benchmark.csv`](../../reports/p4/benchmark.csv) con columnas `variant`, `repetition`,
`warmup`, `latency_ms`, porque así lo espera `app/edge/resource_report.py`. Formato verificado contra
el código real de esa herramienta antes de correr el benchmark (no solo contra la descripción).

## Metodología

`edge/benchmark.py`, corrido en la Raspberry Pi Zero 2W real (no simulado):

- **Misma entrada** para las dos variantes: una sola imagen real de validación
  (`validacion/000005_000004.jpg`, la misma que se usó en P4-10), cargada una vez.
- **10 repeticiones de calentamiento** por variante, descartadas y marcadas `warmup=true` (no
  cuentan como medición válida).
- **100 repeticiones medidas** por variante, `warmup=false` -- cumple el mínimo de
  `MIN_MEASUREMENTS_PER_VARIANT` que exige `resource_report.py`.
- `latency_ms` = preprocesamiento (`to_model_input`) + inferencia (`Model.predict`), igual definición
  que en `main.py`; no incluye envío (P4-12 no existe todavía en este código).
- Mismo runtime y mismos hilos: un solo proceso Python, mismo `onnxruntime.InferenceSession` por
  variante, sin cambios de configuración entre FP32 e INT8 -- la única variable es el modelo.
- Condiciones (temperatura, versión de onnxruntime, memoria pico) registradas en
  [`reports/p4/benchmark_conditions.json`](../../reports/p4/benchmark_conditions.json).

```bash
~/edge-venv/bin/python benchmark.py \
  --image validacion/000005_000004.jpg \
  --fp32 models/model_fp32.onnx --int8 models/model_int8.onnx \
  --out benchmark.csv --warmup 10 --measure 100
```

## Condiciones de la corrida real

| Campo | Valor |
|---|---|
| onnxruntime | 1.31.0, `CPUExecutionProvider` |
| Temperatura CPU antes | 50.5 °C |
| Temperatura CPU después | 68.2 °C (sube por la carga sostenida de las 220 inferencias seguidas) |
| Memoria pico (VmHWM) | 118,500 KB (~116 MB) |
| Filas totales | 220 (110 por variante: 10 calentamiento + 100 medidas) |
| Errores | ninguno -- las dos variantes corrieron sin problema |

## Resultado (validado con `resource_report.py` real de Uriel)

Se corrió `app/edge/resource_report.py` (rama `p4-08-reporte-recursos`) contra nuestro
`benchmark.csv` real para confirmar que se integran de verdad, no solo que el formato coincide sobre
el papel:

| Variante | p50 | p95 | mean | std | muestras |
|---|---|---|---|---|---|
| FP32 | 142.24 ms | 148.13 ms | 143.49 ms | 5.53 ms | 100 |
| INT8 | 70.18 ms | 71.62 ms | 70.42 ms | 0.67 ms | 100 |

- **Reducción de tamaño:** 74.7% (45,224,191 B → 11,430,716 B).
- **Aceleración:** ~2.03x en p50, ~2.07x en p95. `resource_report.py` la marca como
  `significant: true` -- la diferencia (72 ms) supera por mucho la variabilidad combinada de las
  mediciones (~6.2 ms), no es ruido.
- INT8 es también mucho más estable (std 0.67ms vs 5.53ms de FP32).

## Criterios de «hecho»

- [x] 10 ejecuciones de calentamiento descartadas + 100 medidas por variante
- [x] Cada fila: variante, repetición, ms (preprocesamiento + inferencia); envío excluido
- [x] Mismas entradas, runtime, hilos; temperatura/condiciones anotadas (ver tabla arriba)
- [x] Memoria pico registrada (118,500 KB)
- [x] Si el FP32 no corriera, guardar error y configuración -- implementado en `benchmark.py`
  (`<out>_conditions.json`), no se disparó porque ambas variantes corrieron bien
