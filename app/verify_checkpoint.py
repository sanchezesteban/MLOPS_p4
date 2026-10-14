"""Verifica el paquete del Proyecto 3 (issue P4-02).

Carga el checkpoint `best.pt` del candidato `r02` (modelo de origen v1.0.0),
reconstruye la arquitectura con la configuración congelada de la rejilla y
evalúa el split de validación del manifiesto `v0.1.1`. El resultado debe
reproducir `best_val_accuracy = 0.9618320610687023` del `reports/selection.json`
del Proyecto 3.

`app/` no es un paquete instalable: sus módulos se importan como `training.*`
(igual que `app/final.py`), así que se agrega `app/` al path.

Uso:
    uv run python verify_checkpoint.py \
        --checkpoint ../models/p3/r02/best.pt \
        --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
        --crops-root ../data/derived/crops \
        --output ../reports/p4/verify_checkpoint.json
"""

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import torch
from PIL import Image
from sklearn.metrics import accuracy_score, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parent))

from training.model import build_model
from training.preprocess import get_preprocessing_transforms

# Configuración congelada del candidato r02 (app/training/grid.py) y semillas
# de la rejilla (FROZEN_SEEDS). El seed_model no altera las predicciones del
# checkpoint (los pesos se sobreescriben con load_state_dict), pero se deja
# explícito para que la reconstrucción sea idéntica a la del entrenamiento.
R02_CONFIG = SimpleNamespace(hidden_layers=1, dropout=0.3, seed_model=45, image_size=128)


def val_rows(manifest_path: Path) -> pd.DataFrame:
    df = pd.read_csv(manifest_path)
    return df[df["split"] == "val"].reset_index(drop=True)


def evaluate(checkpoint: Path, manifest_path: Path, crops_root: Path) -> dict:
    model = build_model(R02_CONFIG)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    model.eval()

    transform = get_preprocessing_transforms("val", R02_CONFIG.image_size)
    rows = val_rows(manifest_path)

    targets: list[int] = []
    predictions: list[int] = []
    with torch.no_grad():
        for row in rows.itertuples(index=False):
            image = Image.open(crops_root / row.path).convert("RGB")
            tensor = transform(image).unsqueeze(0)
            prediction = int(torch.argmax(model(tensor), dim=1).item())
            targets.append(int(row.label))
            predictions.append(prediction)

    n_cat = sum(1 for t in targets if t == 0)
    n_dog = sum(1 for t in targets if t == 1)
    ok_cat = sum(1 for t, p in zip(targets, predictions, strict=True) if t == 0 and p == 0)
    ok_dog = sum(1 for t, p in zip(targets, predictions, strict=True) if t == 1 and p == 1)
    return {
        "checkpoint": str(checkpoint),
        "manifest": str(manifest_path),
        "split": "val",
        "samples": len(rows),
        "accuracy": accuracy_score(targets, predictions),
        "macro_f1": f1_score(targets, predictions, average="macro", zero_division=0),
        "recall_cat": ok_cat / n_cat if n_cat else 0.0,
        "recall_dog": ok_dog / n_dog if n_dog else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce la accuracy de validación del P3.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--crops-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    metrics = evaluate(args.checkpoint, args.manifest, args.crops_root)
    print(json.dumps(metrics, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(metrics, indent=2) + "\n")


if __name__ == "__main__":
    main()
