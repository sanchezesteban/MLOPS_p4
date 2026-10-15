# P4-09 — Programa de captura e inferencia local en la Pi

**Issue:** [#9](https://github.com/sanchezesteban/MLOPS_p4/issues/9) · **Responsable:** Juan Pablo (@jpdelmuro)
**Ámbito:** rúbrica 2.1, 2.2 — pipeline completo de captura + inferencia corriendo en el dispositivo.

## Resumen

Código en `edge/` (carpeta hermana de `app/`, `backend/`, `frontend/`; no depende de `app/` ni de
`uv`/torch -- en una Pi Zero 2 W de 512 MB esos paquetes no tienen sentido). Dependencias propias en
`edge/requirements.txt`: `onnxruntime`, `opencv-python-headless`, `numpy`, `pillow`.

- `frame_source.py` -- fuente de frame intercambiable: `StubFrameSource` (una imagen fija) o
  `CameraFrameSource` (V4L2 vía OpenCV, `/dev/video0`).
- `preprocess.py` -- recorte fijo (coordenadas en config) → 128×128 RGB → normalización ImageNet.
- `infer.py` -- carga el ONNX con `onnxruntime` (`CPUExecutionProvider`), softmax, SHA-256 del
  artefacto cargado.
- `main.py` -- el programa: por tecla o por intervalo configurable, corre captura → preprocesamiento
  → inferencia, imprime clase/confianza/ms y guarda cada captura como JPEG + JSON local.

## Por qué una fuente de frame intercambiable

La cámara Logitech todavía no está conectada a la Pi (P4-03 sigue abierto en esa parte). En vez de
esperar, `frame_source` en el config decide entre `"stub"` (imagen fija, para desarrollar y probar
todo lo demás) y `"camera"` (real). El día que la cámara llegue, el cambio es de una palabra en el
config -- ningún otro archivo cambia.

## Modelo usado

**Actualización:** Uriel ya entregó los dos `.onnx` reales (fuera de Git/DVC, directo por archivo --
#7/#4 siguen sin estar listos) y están en la Pi, verificados por SHA-256 contra
`reports/p4/conversion_log.json`. `config.json` ya apunta al **INT8 real**
(`models/model_int8.onnx`, `model_version: resnet18-p3-v1.0.0-int8`) como modelo activo. La
validación formal contra la laptop es el documento de P4-10:
[`docs/p4/validacion-pi.md`](validacion-pi.md).

Durante el desarrollo inicial de este ticket (mientras esos archivos no habían llegado) se usó un
placeholder con la misma arquitectura del Proyecto 3 (`resnet18`, cabeza 2 clases, entrada
`1×3×128×128`, salida `1×2`) pero con pesos sin entrenar, tal como contempla el ticket
("mientras, cualquier ONNX con la misma entrada/salida"). Sigue en `models/` por si hace falta
volver a probar el pipeline sin depender de los artefactos reales.

## Cómo correrlo

```bash
cd edge
cp config.example.json config.json   # ajustar model_path, device_id, crop si aplica
python -m venv .venv && source .venv/bin/activate   # o el venv que ya tengas
pip install -r requirements.txt

python main.py --config config.json --once   # una sola captura
python main.py --config config.json          # modo continuo (tecla o intervalo, según config)
```

## Evidencia -- corrida real en la Raspberry Pi Zero 2 W

```
$ ~/edge-venv/bin/python main.py --config config.json --once
Modelo cargado: models/model_int8.onnx (sha256 58effa03a01c...)
Fuente de frame: stub
[60070db7] cat (confianza 0.87, 83.4 ms)
```

JSON local generado (`capturas/60070db7-....json`):

```json
{
  "capture_id": "60070db7-57b0-4844-b527-1c2aa6a30de8",
  "captured_at": "2026-10-14T07:33:24.487171-06:00",
  "device_id": "rpi-zero2w-01",
  "model_version": "resnet18-p3-v1.0.0-int8",
  "model_sha256": "58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb",
  "predicted_class": "cat",
  "confidence": 0.8735,
  "latency_ms": 83.43,
  "crop": { "x": 0, "y": 0, "w": 0, "h": 0 }
}
```

(La predicción en sí no significa nada aquí: la fuente es `stub_frame.jpg`, una imagen sintética de
un solo color, no un gato real -- esto solo verifica que el pipeline completo corre con el modelo
real cargado. La validación con imágenes reales de gato/perro es P4-10, arriba.)

Coincide con el contrato del evento (`docs/p4/contrato-evento.md`): todos los campos que se conocen
en el dispositivo están presentes; `received_at` e `image_key` los agrega AWS al recibir (#16), no
se generan aquí.

También se probó el modo `interval` corriendo varios ciclos seguidos sin caerse ni crecer en uso de
memoria (RAM disponible estable ~285 MB de 415 MB totales en la Pi Zero 2 W).

## Pendiente / siguiente

- `frame_source: "camera"` probado con la Logitech real (#3): **hecho**, ver
  [`docs/p4/hardware.md`](hardware.md).
- Publicar `model_fp32.onnx`/`model_int8.onnx` por DVC (#7) para que no dependan de una copia manual
  entre laptops.
- Validación formal contra la laptop con 10 imágenes reales: **hecha**, ver
  [`docs/p4/validacion-pi.md`](validacion-pi.md) (#10).
- Benchmark formal FP32 vs. INT8 con calentamiento y ≥100 corridas: **P4-11**, siguiente.
