# P4-02 — Verificación del paquete del Proyecto 3 (modelo de origen)

**Issue:** [#2](https://github.com/sanchezesteban/MLOPS_p4/issues/2) · **Responsable:** Uriel (@urielpinag)
**Ámbito:** compuerta **M1** — demostrar que el Proyecto 4 parte del mismo modelo y de la misma validación que el Proyecto 3.

## Resumen

| Criterio | Comando / fuente | Resultado |
|---|---|---|
| SHA-256 del checkpoint | `shasum -a 256` | `f759cde2…ab7d9` ✅ |
| Dataset crudo | `ls data/raw/{images,annotations}` | 600 imágenes · 10 anotaciones ✅ |
| Manifiesto `v0.1.1` reproducible | `dvc repro manifest` | SHA `53fc84fdaa07…` ✅ |
| Accuracy de validación (r02) | `verify_checkpoint.py` | `0.9618320610687023` ✅ |
| Ficha del modelo de origen | `selection.json` + `manifest_meta.json` | run `7e7b4a4b…`, versión `1.0.0` ✅ |
| Binarios fuera de Git | `git check-ignore -v` | `best.pt` e imágenes ignorados ✅ |

El checkpoint del candidato `r02` (versión `1.0.0`) se cargó en la laptop y reprodujo, muestra por muestra, la accuracy de validación del Proyecto 3. Los binarios viven fuera de Git (el dataset y los pesos se versionan con DVC en el issue #7).

## 1. Checkpoint

El `best.pt` del candidato `r02` es el artefacto del run `7e7b4a4b35464cfebb6b41714a3ad931` del Proyecto 3. Se copió a `models/p3/r02/best.pt` (fuera de Git).

```console
$ shasum -a 256 models/p3/r02/best.pt
f759cde23fc314b63c4a4e3c20127ef1eb84121e579b04e7c97911ada20ab7d9  models/p3/r02/best.pt
```

Coincide con `checkpoint_sha256` de `models/registry.json` (entrada `1.0.0`) y con el SHA-256 exigido por el issue.

## 2. Dataset crudo

```console
$ ls data/raw/images | wc -l
600
$ ls data/raw/annotations | wc -l
10
```

## 3. Manifiesto `v0.1.1` reproducible

Se borraron las salidas del manifiesto y se regeneró con DVC:

```console
$ rm -rf data/derived/manifests/v0.1.1 reports/manifests/v0.1.1/*.json
$ .venv-dvc/bin/dvc repro manifest
'data/raw/images.dvc' didn't change, skipping
'data/raw/annotations.dvc' didn't change, skipping
Stage 'crops' didn't change, skipping
Running stage 'manifest':
> uv run python dvc_manifest_stage.py
{"manifest_id": "v0.1.1-53fc84fdaa07", "manifest_sha256": "53fc84fdaa0715f37d90324ae49be39034e2a67bc09ae0a1f1fec8425aeec80f", "rows": 668, "splits": {"train": 464, "val": 131, "test": 73}}
```

El `manifest_sha256` regenerado es `53fc84fdaa0715f37d90324ae49be39034e2a67bc09ae0a1f1fec8425aeec80f`, idéntico al que exige el issue y al de `reports/manifests/v0.1.1/manifest_meta.json`.

## 4. Accuracy de validación reproducida

Script `app/verify_checkpoint.py`. Reconstruye la arquitectura con la configuración congelada del candidato `r02` (`hidden_layers=1`, `dropout=0.3`, `image_size=128`; `app/training/grid.py`), carga el `state_dict` y evalúa el split `val` del manifiesto con el preprocesamiento de validación (`Resize(128) + ImageNet`).

```console
$ cd app
$ uv run --locked --no-build --group ml python verify_checkpoint.py \
    --checkpoint ../models/p3/r02/best.pt \
    --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
    --crops-root ../data/derived/crops \
    --output ../reports/p4/verify_checkpoint.json
{
  "checkpoint": "../models/p3/r02/best.pt",
  "manifest": "../data/derived/manifests/v0.1.1/manifest.csv",
  "split": "val",
  "samples": 131,
  "accuracy": 0.9618320610687023,
  "macro_f1": 0.9618231625575566,
  "recall_cat": 0.9552238805970149,
  "recall_dog": 0.96875
}
```

`accuracy` y `macro_f1` coinciden **hasta el último decimal** con `reports/selection.json` del Proyecto 3 (`best_val_accuracy = 0.9618320610687023`, `best_val_macro_f1 = 0.9618231625575566`). Evidencia cruda: `reports/p4/verify_checkpoint.json`.

## 5. Ficha del modelo de origen

| Campo | Valor |
|---|---|
| `run_id` | `7e7b4a4b35464cfebb6b41714a3ad931` |
| Versión / release | `1.0.0` (candidato `r02`) |
| Clases | `{0: cat, 1: dog}` |
| Entrada | 128 × 128 RGB |
| Normalización | ImageNet (`mean=[0.485,0.456,0.406]`, `std=[0.229,0.224,0.225]`) |
| Arquitectura | ResNet-18 (IMAGENET1K_V1) con cabeza `Linear(512,256)+ReLU+Dropout(0.3)+Linear(256,2)` |
| `checkpoint_sha256` | `f759cde23fc314b63c4a4e3c20127ef1eb84121e579b04e7c97911ada20ab7d9` |
| Dataset / manifiesto | `v0.1.1` · `53fc84fdaa07…` |

Fuentes: `models/registry.json` (entrada `1.0.0`), `reports/selection.json` y `reports/manifests/v0.1.1/manifest_meta.json`.

## 6. Los binarios no entran a Git

```console
$ git check-ignore -v models/p3/r02/best.pt data/raw/images data/derived/crops
.gitignore:32:*.pt	models/p3/r02/best.pt
data/raw/.gitignore:1:/images	data/raw/images
.gitignore:37:data/derived/	data/derived/crops
```

El checkpoint (`*.pt`), las imágenes crudas (`data/raw/images`, vía su `.dvc`) y los derivados (`data/derived/`) quedan ignorados. Se versionan con DVC en el issue #7.

## Cómo reproducirlo

```bash
# 1. Entornos
cd app && uv sync --locked --no-build --group ml && cd ..
uv venv --python 3.12 .venv-dvc && uv pip install --python .venv-dvc 'dvc[s3]==3.67.1'

# 2. Datos y pesos (desde un clon con los binarios del Proyecto 3)
#    data/raw/{images,annotations}, data/derived/ y el best.pt del run 7e7b4a4b…

# 3. Verificaciones
shasum -a 256 models/p3/r02/best.pt
.venv-dvc/bin/dvc repro manifest
cd app && uv run --locked --no-build --group ml python verify_checkpoint.py \
  --checkpoint ../models/p3/r02/best.pt \
  --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
  --crops-root ../data/derived/crops
```

## Nota de infraestructura

El primer commit de `MLOPS_p4` no incluyó los archivos raíz del Proyecto 3 (`.gitignore`, `.gitattributes`, `.dvcignore`, `.dvc/`). Para poder correr DVC y garantizar que los binarios no entren a Git se restauraron desde el clon del Proyecto 3 y se inicializó DVC (sin remotes; el bucket nuevo se configura en #7). `.dvcignore` ahora excluye `__pycache__/`, que cambiaba los hashes de `dvc.lock` tras cada corrida.
