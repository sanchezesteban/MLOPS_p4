# Ficha de entrega — Proyecto 4

**Modelo existente optimizado y clasificación en edge** · Entrega: viernes 16 de octubre de 2026

## Equipo

| Integrante | Frente |
|---|---|
| Esteban | PM: plan, contrato del evento, verificación y entrega |
| Uriel | Modelo: verificación del P3, conversión, calidad, recursos; sección «Capturas Edge» |
| Juan Pablo | Raspberry Pi: hardware, captura, inferencia local, envío, benchmark, estabilidad |
| Ikram | AWS: cuenta, ingesta, API de lectura, despliegue del portal, acceso de evaluación |

## Enlaces

| Qué | Dónde |
|---|---|
| Repositorio | https://github.com/sanchezesteban/MLOPS_p4 |
| Instrucciones | [`README.md`](../../README.md) |
| Autoevaluación (provisional) | [`autoevaluacion.md`](autoevaluacion.md) |
| Portal (sección «Capturas Edge») | http://3.133.248.228 → menú «Capturas Edge» (`/captures`) |
| API de lectura (pública, solo lectura) | `GET https://el1c2mr69k.execute-api.us-east-2.amazonaws.com/captures?limit=50` |
| Video de demostración (extra) | https://drive.google.com/file/d/1GxSCgOiC9ObiwqF4v6KCUMN8vCCcly-3/view |

## Acceso de evaluación a AWS (solo lectura)

| Dato | Valor |
|---|---|
| Consola | https://595981034933.signin.aws.amazon.com/console |
| Usuario | `mlops-p4-evaluador` |
| Contraseña | **Se entrega por privado** (no se publica en el repositorio) |
| Región | `us-east-2` (Ohio) |
| Vigencia | Hasta el 2026-11-17 23:59 UTC |
| Puede ver | Buckets `mlops-p4-models-595981034933` y `mlops-p4-captures-595981034933`, tabla DynamoDB `mlops-p4-captures`, logs de la ingesta, la lectura y la API, configuración de las Lambdas |
| No puede | Escribir, borrar, cambiar recursos ni administrar IAM |

Detalle y prueba de permisos: [`aws.md`](aws.md) («Acceso de evaluación»).

## Demostración

- **Modalidad:** **PENDIENTE** (presencial o remota; fecha y hora por confirmar).
- **Opera el dispositivo:** Juan Pablo. **AWS (fallo controlado y consultas):** Ikram.
- **Guion:** [`guion-demo.md`](guion-demo.md).

## Modelo y optimización

| Dato | Original (Proyecto 3) | Variante desplegada |
|---|---|---|
| Identidad | Versión `1.0.0`, candidato `r02`, run `7e7b4a4b35464cfebb6b41714a3ad931` | `resnet18-p3-v1.0.0-int8` |
| Archivo | `models/p3/r02/best.pt` (DVC) | `models/p3/r02/onnx/model_int8.onnx` (DVC) |
| SHA-256 | `f759cde23fc314b63c4a4e3c20127ef1eb84121e579b04e7c97911ada20ab7d9` | `58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb` |
| Formato | PyTorch FP32 (ONNX FP32 `7a00948a…` para comparar en la Pi) | ONNX INT8, QDQ, opset 17 |
| Técnica | — | Cuantización estática (pesos QInt8 por canal, activaciones QUInt8), calibrada con 464 recortes de train |
| Clases y entrada | `{0: cat, 1: dog}`, 128×128 RGB, normalización ImageNet | Igual |
| Recuperación | `dvc pull` (remote `p4`, `s3://mlops-p4-models-595981034933/dvc`) | Igual |

### Dónde descargar cada artefacto

Los pesos no van en Git: se versionan con DVC en el bucket del proyecto. Con el usuario de
evaluación se descargan desde la consola de S3 (bucket `mlops-p4-models-595981034933`); con una
llave del equipo, con `dvc pull`.

| Artefacto | Objeto en S3 | Tamaño | SHA-256 |
|---|---|---|---|
| `best.pt` (original, P3) | `dvc/files/md5/1d/9a6b66d4a12d93ee3cc440047d03ec` | 45 304 641 B | `f759cde2…ab7d9` |
| `model_fp32.onnx` | `dvc/files/md5/10/dfddc13c23b94f4ae26e810f5ae0eb` | 45 224 191 B | `7a00948a…7c78` |
| `model_int8.onnx` (desplegado) | `dvc/files/md5/d1/da489b980cb3364ce3511f355cf263` | 11 430 716 B | `58effa03…a1bb` |

Referencias del Proyecto 3 para contrastar la continuidad: `reports/selection.json`,
`reports/manifests/v0.1.1/manifest_meta.json`, `docs/seleccion-candidato.md` y
`docs/evaluacion-final.md`.

## Hardware y runtime

Raspberry Pi Zero 2 W (4× Cortex-A53, 512 MB) · Raspberry Pi OS Lite 64-bit (Debian 13) ·
microSD 32 GB · cámara Logitech C920 USB (adaptador OTG) · Python 3.13.5 · onnxruntime 1.31.0
(`CPUExecutionProvider`). Ficha completa: [`hardware.md`](hardware.md).

## Resultados

| Dato | Original | Optimizado | Diferencia |
|---|---|---|---|
| Tamaño | 45 224 191 B (ONNX FP32) | 11 430 716 B | −74.7 % |
| Accuracy, val P3 (131 recortes) | 0.961832 | 0.961832 | 0.00 pp |
| F1 macro, val P3 | 0.961823 | 0.961823 | 0.00 |
| Latencia en la Pi p50 / p95 | 142.24 / 148.13 ms | 70.18 / 71.62 ms | 2.03× más rápido |
| Mediciones válidas / calentamiento | 100 / 10 | 100 / 10 | — |

## Evidencias por requisito de la rúbrica

| Criterio | Evidencia |
|---|---|
| M1 · 1.1 Continuidad con el modelo del P3 | [`modelo-origen.md`](modelo-origen.md), `reports/p4/verify_checkpoint.json` (accuracy val reproducida 0.9618), [`artefactos.md`](artefactos.md) |
| 1.2 Optimización real y variante ejecutable | `app/edge/convert.py`, [`conversion-onnx.md`](conversion-onnx.md), `reports/p4/conversion_log.json` |
| 1.3 Calidad comparada | `reports/p4/quality_predictions.csv` (una fila por muestra), `reports/p4/quality_metrics.json`, `reports/p4/calibracion_ids.txt`, [`quality-comparison.md`](quality-comparison.md) |
| M2 · 2.1–2.3 Cámara e inferencia local en la Pi | [`captura-inferencia.md`](captura-inferencia.md), [`validacion-pi.md`](validacion-pi.md) (laptop INT8 = Pi INT8 en 10/10; prueba real sin red) |
| 2.4 Operación estable | [`estabilidad-procedimiento.md`](estabilidad-procedimiento.md), `docs/p4/evidencia/estabilidad/` (5 min, reinicio, 56 capturas) |
| 3.1–3.3 Recursos y mejora | `reports/p4/benchmark.csv`, `reports/p4/benchmark_conditions.json`, `reports/p4/resources.json`, [`reporte-optimizacion.md`](reporte-optimizacion.md) |
| 4.1–4.3 Envío, persistencia, fallo y reintento | [`contrato-evento.md`](contrato-evento.md), [`envio-aws.md`](envio-aws.md), [`aws.md`](aws.md), `evidencias/aws/eventos.csv` y `eventos.json` |
| M3 · 5.1–5.3 Portal | [`capturas-edge.md`](capturas-edge.md), [`capturas-api-real.md`](capturas-api-real.md) (cruce con la captura oficial `8d026b3c-08ed-4770-9632-0ecd2d38b843`) |
| 6.1–6.3 Reproducción y configuración | [`README.md`](../../README.md), [`verificacion-manual.md`](verificacion-manual.md), `edge/config.example.json` |

## Capturas oficiales

56 capturas de la Pi (`rpi-zero2w-01`), 31 `cat` y 25 `dog`, todas con imagen en S3:
`evidencias/aws/eventos.csv` / `eventos.json`. Lista de IDs de la sesión:
`docs/p4/evidencia/estabilidad/capture_ids.txt`. Las capturas de prueba anteriores se eliminaron
de AWS el 16-oct; las de la demostración se agregan a las anteriores.
