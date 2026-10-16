# P4-12 — Envío a AWS con estado visible y reintento sin duplicados

**Issue:** [#12](https://github.com/sanchezesteban/MLOPS_p4/issues/12) · **Responsable:** Juan Pablo (@jpdelmuro)
**Ámbito:** rúbrica 4.1, 4.3.

## Resumen

- `edge/send.py`: firma SigV4 (misma lógica que `app/edge_ingest/simulate.py`, el simulador de
  Ikram para #16, pero para el dispositivo real -- no comparten código, cada uno vive en su propio
  codebase). `201` y `200` (reintento del mismo `capture_id`) cuentan como `enviado`; cualquier otra
  respuesta, o no tener red, es `error`. Nunca lanza una excepción hacia afuera.
- `edge/capture_log.py`: bitácora `log.jsonl` append-only -- un registro por intento (nunca se
  reescribe una línea), con `send_status` (`pendiente`/`enviado`/`error`), `send_error` y `send_ms`.
  El estado actual de una captura es el de su línea más reciente.
- `edge/main.py`: cada captura intenta mandarse automáticamente si `api_url` está en el config,
  **pero la clasificación nunca depende de que el envío funcione** -- un fallo de red solo se
  registra, nunca detiene ni hace fallar la captura siguiente. `--retry <capture_id>` reintenta una
  captura guardada localmente (reusa el mismo `capture_id`, así AWS lo reconoce como duplicado, no
  como un evento nuevo); `--retry-failed` reintenta todas las que quedaron en `error`.
- `edge/config.example.json`: `api_url`, `aws_region`, `aws_profile`, `send_timeout_s`, `log_path`.
- Se borró `app/edge/.env.pi.example` (quedaba duplicado con el config de `edge/`, que es el que
  realmente usa el dispositivo).
- La credencial real del dispositivo (`mlops-p4-device-rpi-zero2w-01`, entregada por Ikram) ya está
  configurada tanto en la Pi como en esta laptop, perfil `mlops-p4-device`.

## Validado contra la infraestructura real (no simulada)

### Envío exitoso

```
$ ~/edge-venv/bin/python main.py --config config.json --once
Modelo cargado: models/model_int8.onnx (sha256 58effa03a01c...)
Fuente de frame: camera
[59d0be4a] cat (confianza 0.90, 125.0 ms) -- enviado (4887.8 ms)
```

Confirmado directo en AWS con una credencial de solo lectura (no la del dispositivo, que no puede
leer):

```
$ aws dynamodb get-item --table-name mlops-p4-captures \
    --key '{"capture_id":{"S":"59d0be4a-..."}}' --profile mlops-p4 --region us-east-2
# -> un ítem real, con received_at e image_key agregados por AWS, crop: NULL
$ aws s3api head-object --bucket mlops-p4-captures-595981034933 \
    --key captures/2026/10/16/59d0be4a-....jpg --profile mlops-p4 --region us-east-2
# -> ContentLength 5427, ServerSideEncryption AES256, VersionId presente
```

### Reintento del mismo `capture_id`: no duplica

```
$ ~/edge-venv/bin/python main.py --config config.json --retry 59d0be4a-2f4b-4816-8e49-81e6612e0942
[59d0be4a] cat (confianza 0.90, 125.0 ms) -- enviado (548.4 ms)
```

`aws dynamodb get-item` sobre el mismo `capture_id` sigue devolviendo **un solo ítem** (no dos) --
la escritura condicional de Ikram (`attribute_not_exists(capture_id)`) funciona de verdad.

### Sin red: sigue clasificando, los envíos quedan en `error`, luego se reintentan solos

Mismo procedimiento de P4-10 (`tmux` + `systemd-run` para apagar el wifi sin matar el propio
comando de reconexión). Con `main.py` corriendo en modo intervalo y `api_url` configurada:

- **7 capturas durante el corte de red**: todas clasificaron bien (ninguna se detuvo ni crasheó),
  todas quedaron en `send_status: error` con `"0 sin conexión: [Errno -3] Temporary failure in name
  resolution"`.
- **2 capturas después de que volvió la red**: ambas `enviado` en el primer intento.
- `--retry-failed`: reintentó las 7 que habían quedado en error, **las 7 se mandaron bien** (confirmado
  individualmente contra DynamoDB). Una segunda corrida de `--retry-failed` reporta "No hay capturas
  en estado error."

Log completo de esa prueba: [`evidencia/log-sin-red-ejemplo.jsonl`](evidencia/log-sin-red-ejemplo.jsonl)
(17 líneas: `pendiente`+`error` × 7, `pendiente`+`enviado` × 2).

## Pendiente

- **Prueba del fallo controlado con Ikram** (`scripts/p4_ingesta_fallo.sh off/on`): ese script necesita
  un perfil de **administrador** de la cuenta (nosotros solo tenemos el perfil de lectura y el del
  dispositivo), así que hay que coordinarlo con Ikram para correrlo juntos. El comportamiento esperado
  ya está cubierto por la prueba de "sin red" de arriba (misma ruta de código: cualquier respuesta que
  no sea 200/201 cae en `error` con `send_error` describiendo el código real) -- falta el caso puntual
  de un 5xx real de Lambda, que es justo lo que simula ese script.

## Criterios de «hecho»

- [x] `capture_id` se genera una vez y se reutiliza en cada reintento
- [x] Estado por captura: pendiente / enviado / error, con el mensaje de error visible (`log.jsonl`)
- [x] Reintento manual de una captura fallida con el mismo ID (`--retry`, `--retry-failed`)
- [x] La clasificación no se detiene si no hay red (probado de verdad, 7 capturas durante el corte)
- [x] Tiempo de envío medido por separado de la inferencia (`send_ms` en el log, `latency_ms` en el
  evento son campos distintos)
- [x] Credenciales fuera del código (perfil de AWS local, nunca en Git -- `aws_profile` en el config
  solo nombra el perfil, no contiene la llave)
