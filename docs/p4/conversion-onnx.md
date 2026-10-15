# P4-05 — Conversión PyTorch → ONNX FP32 → ONNX INT8

**Issue:** [#5](https://github.com/sanchezesteban/MLOPS_p4/issues/5) · **Responsable:** Uriel (@urielpinag)
**Ámbito:** rúbrica 1.2, 1.3 — generar la variante optimizada a partir de los pesos del P3.

## Resumen

Script único `app/edge/convert.py`: recibe el `best.pt` del candidato `r02` (v1.0.0) y produce **dos** artefactos ONNX: el FP32 y el INT8 por cuantización estática de ONNX Runtime. La calibración usa **solo** recortes de `train`.

| Artefacto | SHA-256 | Tamaño |
|---|---|---|
| `best.pt` (entrada) | `f759cde23fc314b63c4a4e3c20127ef1eb84121e579b04e7c97911ada20ab7d9` | 45 304 641 B |
| `model_fp32.onnx` | `7a00948a4f611b3ddb0f8adecdf8bc919dad81bb78ff2bc8de50b4541bdf7c78` | 45 224 191 B |
| `model_int8.onnx` | `58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb` | 11 430 716 B |

Reducción de tamaño FP32 → INT8: **−74.7 %**. Los ONNX **no** entran a Git (`*.onnx` ignorado); se publican con DVC en el issue #7.

## Cómo se generó

```console
$ cd app
$ uv run --locked --no-build --group ml python edge/convert.py \
    --checkpoint ../models/p3/r02/best.pt \
    --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
    --crops-root ../data/derived/crops \
    --out-dir ../models/p3/r02/onnx \
    --report-dir ../reports/p4
```

- **Entrada del modelo:** `1 × 3 × 128 × 128` RGB; normalización ImageNet.
- **OPset:** 17.
- **FP32:** `torch.onnx.export`.
- **INT8:** `onnxruntime.quantization.quantize_static`, formato `QDQ`, `per_channel=True`, pesos `QInt8`, activaciones `QUInt8`.

## Calibración (sin fuga)

- Split usado: **`train`** únicamente (464 recortes).
- IDs guardados en `reports/p4/calibracion_ids.txt` (SHA-256 del listado: `297382f18e7c5fa78400e5c74b44561e620672447965cc7b66007dfc10effc25`).
- Verificado: `calib == train` (464 = 464), `calib ∩ val = 0`, `calib ∩ test = 0`. Ningún dato de `val` ni `test` entra a la conversión ni a sus decisiones.

## Prueba de consistencia

Una imagen de train conocida (`images/000003_000006.jpg`, tomada del **primer ID de `calibracion_ids.txt`**) da la misma clase en los tres:

```json
{ "pytorch_class": 0, "fp32_class": 0, "int8_class": 0, "all_agree": true }
```

## Registro

`reports/p4/conversion_log.json` guarda SHA-256 de entrada y salidas, versiones (`torch 2.14.0`, `onnx 1.23.2`, `onnxruntime 1.31.0`, `numpy 2.5.3`), opset y configuración de cuantización. Ambos `.onnx` pasan `onnx.checker.check_model`.

## Pendiente / siguiente

- La comparación formal de calidad (accuracy/F1 y caída en pp) es el issue **#6**.
- El **FP32** se entrega a Juan Pablo para el desarrollo en la Pi (#9/#10); el INT8 se usa en #10/#11.
