"""Comparación de calidad original vs. optimizado (issue P4-06).

Evalúa, sobre la **misma validación del Proyecto 3** (split `val` del manifiesto
`v0.1.1`), tres modelos con la misma entrada y el mismo preprocesamiento:

- `original`: PyTorch `best.pt` del candidato `r02` (modelo de origen v1.0.0).
- `fp32`: ONNX FP32 (fidelidad de la exportación).
- `optimized`: ONNX INT8 (variante a desplegar en la Pi).

Escribe una fila por muestra en `reports/p4/quality_predictions.csv` y las
métricas en `reports/p4/quality_metrics.json`: accuracy, F1 macro, métricas por
clase y la caída de accuracy en puntos porcentuales (meta ≤ 2 pp).

`app/` no es un paquete instalable: sus módulos se importan como `training.*`,
por eso se agrega `app/` al path.

Uso (desde `app/`):

    uv run --locked --no-build --group ml python edge/compare_quality.py \
        --checkpoint ../models/p3/r02/best.pt \
        --fp32 ../models/p3/r02/onnx/model_fp32.onnx \
        --int8 ../models/p3/r02/onnx/model_int8.onnx \
        --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
        --crops-root ../data/derived/crops \
        --report-dir ../reports/p4
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import onnxruntime as ort
import pandas as pd
import torch
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.model import build_model
from training.preprocess import get_preprocessing_transforms

R02_CONFIG = SimpleNamespace(hidden_layers=1, dropout=0.3, seed_model=45, image_size=128)
CLASS_NAMES = {0: "cat", 1: "dog"}
TARGET_ACCURACY_DROP_PP = 2.0


def load_checkpoint(checkpoint: Path) -> torch.nn.Module:
    model = build_model(R02_CONFIG)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    model.eval()
    return model


class OnnxModel:
    def __init__(self, path: Path) -> None:
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def predict(self, tensor: torch.Tensor) -> int:
        logits = self.session.run(None, {self.input_name: tensor.numpy().astype(np.float32)})[0]
        return int(np.argmax(logits, axis=1)[0])


def class_metrics(targets: list[int], predictions: list[int]) -> dict:
    precision, recall, f1, support = precision_recall_fscore_support(
        targets, predictions, labels=[0, 1], zero_division=0
    )
    return {
        "accuracy": accuracy_score(targets, predictions),
        "macro_f1": f1_score(targets, predictions, average="macro", zero_division=0),
        "per_class": {
            CLASS_NAMES[label]: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate([0, 1])
        },
        "confusion_matrix": {
            "labels": [CLASS_NAMES[0], CLASS_NAMES[1]],
            "rows_true_cols_pred": confusion_matrix(targets, predictions, labels=[0, 1]).tolist(),
        },
    }


def evaluate(
    checkpoint: Path, fp32: Path, int8: Path, manifest: Path, crops_root: Path, split: str
) -> tuple[list[dict], dict]:
    model = load_checkpoint(checkpoint)
    onnx_fp32 = OnnxModel(fp32)
    onnx_int8 = OnnxModel(int8)
    transform = get_preprocessing_transforms("val", R02_CONFIG.image_size)

    df = pd.read_csv(manifest)
    rows = df[df["split"] == split].reset_index(drop=True)

    records: list[dict] = []
    for row in rows.itertuples(index=False):
        tensor = transform(Image.open(crops_root / row.path).convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            original = int(torch.argmax(model(tensor), dim=1).item())
        records.append(
            {
                "crop_id": row.crop_id,
                "true_label": int(row.label),
                "true_class": CLASS_NAMES[int(row.label)],
                "original_pred": original,
                "fp32_pred": onnx_fp32.predict(tensor),
                "optimized_pred": onnx_int8.predict(tensor),
            }
        )

    targets = [record["true_label"] for record in records]
    metrics = {
        "split": split,
        "samples": len(records),
        "target_accuracy_drop_pp": TARGET_ACCURACY_DROP_PP,
        "original": class_metrics(targets, [r["original_pred"] for r in records]),
        "fp32": class_metrics(targets, [r["fp32_pred"] for r in records]),
        "optimized": class_metrics(targets, [r["optimized_pred"] for r in records]),
    }
    drop_pp = (metrics["original"]["accuracy"] - metrics["optimized"]["accuracy"]) * 100
    metrics["accuracy_drop_pp"] = drop_pp
    metrics["within_target"] = drop_pp <= TARGET_ACCURACY_DROP_PP
    return records, metrics


def error_analysis(records: list[dict]) -> dict:
    """Muestras donde INT8 difiere de PyTorch y a qué clase pertenecen."""
    original_vs_optimized = [r for r in records if r["original_pred"] != r["optimized_pred"]]
    by_true_class: dict[str, int] = {}
    for record in original_vs_optimized:
        by_true_class[record["true_class"]] = by_true_class.get(record["true_class"], 0) + 1
    return {
        "disagreements": [
            {
                "crop_id": r["crop_id"],
                "true_class": r["true_class"],
                "original_pred": CLASS_NAMES[r["original_pred"]],
                "optimized_pred": CLASS_NAMES[r["optimized_pred"]],
            }
            for r in original_vs_optimized
        ],
        "disagreements_by_true_class": by_true_class,
    }


def write_predictions(path: Path, records: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["crop_id", "true_class", "original_pred", "optimized_pred", "fp32_pred"])
        for record in records:
            writer.writerow(
                [
                    record["crop_id"],
                    record["true_class"],
                    CLASS_NAMES[record["original_pred"]],
                    CLASS_NAMES[record["optimized_pred"]],
                    CLASS_NAMES[record["fp32_pred"]],
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Calidad original (PyTorch) vs. ONNX INT8.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--fp32", type=Path, required=True)
    parser.add_argument("--int8", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--crops-root", type=Path, required=True)
    parser.add_argument("--split", default="val")
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()

    args.report_dir.mkdir(parents=True, exist_ok=True)
    records, metrics = evaluate(
        args.checkpoint, args.fp32, args.int8, args.manifest, args.crops_root, args.split
    )
    metrics["error_analysis"] = error_analysis(records)

    write_predictions(args.report_dir / "quality_predictions.csv", records)
    (args.report_dir / "quality_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
