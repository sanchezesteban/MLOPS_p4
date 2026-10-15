# P4-07 — Publicación de artefactos con DVC en el S3 nuevo

**Issue:** [#7](https://github.com/sanchezesteban/MLOPS_p4/issues/7) · **Responsable:** Uriel (@urielpinag)
**Ámbito:** rúbrica 1.1, 3.2 — hacer recuperables los pesos y el dataset sin meterlos a Git.

## Remote

| Dato | Valor |
|---|---|
| Remote DVC | `p4` → `s3://mlops-p4-models-595981034933/dvc` (default) |
| Región | `us-east-2` |
| Remotes viejos | eliminados (el `.dvc/config` del P4 solo tiene `p4`) |
| Credenciales | perfil `mlops-p4` en `.dvc/config.local` (**ignorado por Git**) |

## Tabla de versiones

| Artefacto | Ruta | SHA-256 | Tamaño (bytes) | DVC md5 |
|---|---|---|---|---|
| Checkpoint original (`best.pt`) | `models/p3/r02/best.pt` | `f759cde23fc314b63c4a4e3c20127ef1eb84121e579b04e7c97911ada20ab7d9` | 45 304 641 | `1d9a6b66d4a12d93ee3cc440047d03ec` |
| ONNX FP32 | `models/p3/r02/onnx/model_fp32.onnx` | `7a00948a4f611b3ddb0f8adecdf8bc919dad81bb78ff2bc8de50b4541bdf7c78` | 45 224 191 | `10dfddc13c23b94f4ae26e810f5ae0eb` |
| ONNX INT8 | `models/p3/r02/onnx/model_int8.onnx` | `58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb` | 11 430 716 | `d1da489b980cb3364ce3511f355cf263` |
| Dataset — imágenes (600) | `data/raw/images` | `-dir-` | 13 556 278 | `951150dd4fb053f4665089fcb37a1c87.dir` |
| Dataset — anotaciones (10) | `data/raw/annotations` | `-dir-` | 256 669 | `c7cb86ae7ece94ef7b853620e464a4d7.dir` |

Cada uno tiene su `.dvc`: `models/p3/r02/best.pt.dvc`, `models/p3/r02/onnx/model_fp32.onnx.dvc`, `models/p3/r02/onnx/model_int8.onnx.dvc`, `data/raw/images.dvc`, `data/raw/annotations.dvc`.

## Cómo recuperarlos en un clon limpio

```bash
git clone git@github.com:sanchezesteban/MLOPS_p4.git && cd MLOPS_p4
uv venv --python 3.12 .venv-dvc && uv pip install --python .venv-dvc 'dvc[s3]==3.67.1'
dvc remote modify --local p4 profile mlops-p4   # tu perfil con la llave del equipo
dvc pull                                        # baja best.pt, ONNX y dataset
```

`dvc status --cloud` debe responder `Cache and remote 'p4' are in sync.`

## `models/registry.json`

Se añadió la versión `1.0.0-int8` (conforme al esquema `ModelEntry` que consume el portal) apuntando al artefacto DVC del ONNX INT8 en el bucket nuevo, con su `sha256`, `VersionId` y `checkpoint_sha256`.

## Nota de limpieza

El primer commit traía `mlflow-store.dvc` (el MLflow del Proyecto 3, 541 MB). No es artefacto del P4 y su contenido no existe en el clon; se eliminó para que `dvc pull` no intente traer un objeto inexistente. El código que usa `mlflow-store/` lo lee solo si está presente (variable `MLFLOW_SNAPSHOT`).
