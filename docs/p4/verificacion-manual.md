# Verificación manual con resultados (P4-21)

Comprobaciones repetibles del recorrido completo (rúbrica 6.2). Cada una indica cómo correrla,
qué se espera y qué se obtuvo, con fecha, responsable y evidencia. El evaluador puede elegir
cualquier entrada o `capture_id` de la tabla de muestras al final y repetirla.

Comandos de `app/` con `uv run …` desde `app/`; comandos de la Pi desde `~/edge` con
`~/edge-venv/bin/python`.

## A. Modelo y conversión

| # | Comprobación | Cómo | Esperado | Obtenido | Fecha · quién | Evidencia |
|---|---|---|---|---|---|---|
| A1 | El checkpoint es el del P3 | `sha256sum models/p3/r02/best.pt` | `f759cde2…ab7d9` | Coincide | 13-oct · Uriel | [`modelo-origen.md`](modelo-origen.md) |
| A2 | Misma validación del P3 | `dvc repro manifest` | `manifest_sha256` `53fc84fd…` | Coincide | 13-oct · Uriel | [`modelo-origen.md`](modelo-origen.md) |
| A3 | El checkpoint reproduce su accuracy | `python verify_checkpoint.py …` | 0.9618320610687023 (131 val) | Idéntico | 13-oct · Uriel | `reports/p4/verify_checkpoint.json` |
| A4 | Conversión carga y es consistente | `python edge/convert.py …` | `check_model` OK; misma clase en PyTorch, FP32 e INT8 | OK, `all_agree: true` | 13-oct · Uriel | `reports/p4/conversion_log.json` |
| A5 | Calibración sin fuga | Cruzar `calibracion_ids.txt` con val y test | 464 IDs de train, 0 cruces | 0 con val, 0 con test, 0 duplicados | 13-oct · Esteban (revisión) | `reports/p4/calibracion_ids.txt` |
| A6 | Calidad recalculable | Recalcular desde `quality_predictions.csv` | 131 filas; acc y F1 = JSON | 0.9618 / 0.9618 en original e INT8; 0.00 pp | 14-oct · Esteban (revisión) | `reports/p4/quality_*.{csv,json}` |
| A7 | Artefacto desplegado = publicado | `sha256sum models/model_int8.onnx` en la Pi | `58effa03…` | Coincide (también lo imprime `main.py` al arrancar) | 15-oct · Juan Pablo | [`validacion-pi.md`](validacion-pi.md) |

## B. Inferencia en la Pi

| # | Comprobación | Cómo | Esperado | Obtenido | Fecha · quién | Evidencia |
|---|---|---|---|---|---|---|
| B1 | Preprocesamiento idéntico al del P3 | `python -m pytest edge/test_preprocess.py`; comparar contra el resize de PIL | Diferencia ≈ 0 | 3/3 pruebas; diferencia máx. 1.5e-8 | 15-oct · Esteban (revisión) | `edge/test_preprocess.py` |
| B2 | Entradas conocidas: laptop vs. Pi | 10 recortes de val en laptop INT8 y Pi INT8 | Misma clase | 10/10, misma clase **y** misma confianza | 15-oct · Juan Pablo | [`validacion-pi.md`](validacion-pi.md) |
| B3 | Responde a objetos reales distintos | Gato y perro frente a la cámara | Predicciones distintas y correctas | `cat` 0.74 / `dog` 0.89 | 15-oct · Juan Pablo | `docs/p4/evidencia/camara-*.jpg` |
| B4 | Sin red sigue clasificando | `bash edge/sin_red_demo.sh 65` | Capturas continúan durante el corte | 17 capturas seguidas en 86 s con Wi-Fi apagado | 15-oct · Juan Pablo | [`validacion-pi.md`](validacion-pi.md) |
| B5 | 5 minutos y reinicio | `main.py` en intervalo 5 min; reiniciar y `--once` | Sin caídas; captura nueva llega | 55 capturas, 0 errores; `8d026b3c…` llega tras reinicio | 16-oct · Juan Pablo | [`estabilidad-procedimiento.md`](estabilidad-procedimiento.md) |
| B6 | Benchmark recalculable | Recalcular p50/p95 de `benchmark.csv` | 10+100 por variante | FP32 142.24/148.13, INT8 70.18/71.62 ms | 16-oct · Ikram y Esteban | `reports/p4/benchmark.csv`, `resources.json` |

## C. Envío y AWS

| # | Comprobación | Cómo | Esperado | Obtenido | Fecha · quién | Evidencia |
|---|---|---|---|---|---|---|
| C1 | Envío y persistencia | `main.py --once`; `evidence.py get <id>` | 201; ítem en DynamoDB y JPEG en S3 | OK | 16-oct · Juan Pablo | [`envio-aws.md`](envio-aws.md) |
| C2 | Reintento sin duplicar | `main.py --retry <id>` | 200 `duplicate: true`; un solo ítem | OK | 16-oct · Juan Pablo | [`envio-aws.md`](envio-aws.md) |
| C3 | Fallo controlado y reintento | `p4_ingesta_fallo.sh off` → captura → `on` → `--retry-failed` | `error` 503 visible → `enviado`; un solo ítem | 503 → 201; un registro | 16-oct · Juan Pablo e Ikram | [`envio-aws.md`](envio-aws.md) |
| C4 | Sin red: envío marcado y reintentado | Corte de red con `api_url` activa | `error` sin detener; luego `--retry-failed` | 7 en `error` → 7 `enviado` | 16-oct · Juan Pablo | `docs/p4/evidencia/log-sin-red-ejemplo.jsonl` |
| C5 | Validación de la ingesta | Pruebas de `app/` | Rechaza campos inválidos | 46/46 pruebas de ingesta, lectura, evidencia y reporte | 15-oct · Esteban (revisión) | `app/tests/test_edge_*.py` |
| C6 | Export coincide con la sesión | Cruzar `eventos.csv` con `capture_ids.txt` | Mismos 56 IDs | Idénticos; 31 cat / 25 dog; 56 imágenes en S3; mismo SHA del modelo | 16-oct · Esteban (revisión) | `evidencias/aws/eventos.csv` |
| C7 | Acceso de evaluación limitado | `aws iam simulate-principal-policy` | Lectura permitida; escritura denegada | Según lo esperado | 14-oct · Ikram | [`aws.md`](aws.md) |

## D. Portal

| # | Comprobación | Cómo | Esperado | Obtenido | Fecha · quién | Evidencia |
|---|---|---|---|---|---|---|
| D1 | Sección dentro del portal | Abrir http://3.133.248.228 → «Capturas Edge» | En el menú del portal P1–P3 | OK | 16-oct · Uriel | `docs/p4/capturas-edge-real.png` |
| D2 | Metadatos coinciden con AWS | Comparar `8d026b3c…` en portal, `GET /captures` y `eventos.json` | Iguales campo por campo | Iguales | 16-oct · Uriel | [`capturas-api-real.md`](capturas-api-real.md) |
| D3 | Captura nueva al actualizar | `bash edge/verificar_captura.sh <id>` y botón «Actualizar» | Aparece arriba | OK | 16-oct · Uriel y Juan Pablo | [`capturas-api-real.md`](capturas-api-real.md) |
| D4 | Nunca datos de ejemplo en producción | Compilar sin `VITE_CAPTURES_API_URL` | Mensaje de error | «API de capturas no configurada.» | 15-oct · Esteban (revisión) | `docs/p4/capturas-edge-sin-api.png` |
| D5 | Pruebas del portal | `cd frontend && npm test` | Todas pasan | 190/190 | 15-oct · Esteban (revisión) | `frontend/src/captures/` |

## Muestras para que el evaluador elija

| Tipo | Valores |
|---|---|
| Recortes de validación (B2) | `000005_000004`, `000010_000008`, `000039_000064`, `000625_000624`, `000633_000627` (error conocido del modelo: cat → dog en original e INT8) |
| Capturas oficiales en AWS | `8d026b3c-08ed-4770-9632-0ecd2d38b843` (reinicio) o cualquiera de `evidencias/aws/eventos.csv` |
