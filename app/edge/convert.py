"""Conversión reproducible PyTorch -> ONNX FP32 -> ONNX INT8 (issue P4-05).

Toma el `best.pt` del candidato `r02` (modelo de origen v1.0.0), exporta un
ONNX FP32 y, a partir de él, un ONNX INT8 por cuantización estática con ONNX
Runtime. La calibración usa **solo** recortes del split `train` del manifiesto
`v0.1.1`; sus IDs se guardan en `calibracion_ids.txt` como evidencia de que no
se tocó `val` ni `test`.

`app/` no es un paquete instalable: sus módulos se importan como `training.*`
(igual que `app/final.py`), por eso se agrega `app/` al path.

Uso (desde `app/`):

    uv run --locked --no-build --group ml python edge/convert.py \
        --checkpoint ../models/p3/r02/best.pt \
        --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
        --crops-root ../data/derived/crops \
        --out-dir ../models/p3/r02/onnx \
        --report-dir ../reports/p4
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
import torch
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.model import build_model
from training.preprocess import get_preprocessing_transforms

# Configuración congelada del candidato r02 (app/training/grid.py) y semillas de
# la rejilla (FROZEN_SEEDS). Igual que en app/verify_checkpoint.py.
R02_CONFIG = SimpleNamespace(hidden_layers=1, dropout=0.3, seed_model=45, image_size=128)

OPSET_DEFAULT = 17


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model(checkpoint: Path) -> torch.nn.Module:
    model = build_model(R02_CONFIG)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    model.eval()
    return model


def export_fp32(model: torch.nn.Module, output: Path, opset: int) -> None:
    dummy = torch.randn(1, 3, R02_CONFIG.image_size, R02_CONFIG.image_size)
    torch.onnx.export(
        model,
        dummy,
        str(output),
        input_names=["input"],
        output_names=["logits"],
        opset_version=opset,
        dynamo=False,
    )


class TrainCalibrationReader(CalibrationDataReader):
    """Alimenta a `quantize_static` tensores `1x3x128x128` de recortes de train."""

    def __init__(self, samples: list[dict[str, np.ndarray]]) -> None:
        self._iterator = iter(samples)

    def get_next(self) -> dict[str, np.ndarray] | None:
        return next(self._iterator, None)


def calibration_samples(
    manifest_path: Path, crops_root: Path, limit: int
) -> tuple[list[dict[str, np.ndarray]], list[str]]:
    """Devuelve las muestras de calibración (solo split `train`) y sus crop_id.

    Usa el preprocesamiento determinista de evaluación (`Resize` + ImageNet),
    que es el mismo que verá el modelo en la Pi; evita el `RandomResizedCrop`
    del split de entrenamiento para no meter ruido de aumento a la calibración.
    """
    df = pd.read_csv(manifest_path)
    train = df[df["split"] == "train"].reset_index(drop=True)
    if limit > 0:
        train = train.head(limit)

    transform = get_preprocessing_transforms("val", R02_CONFIG.image_size)
    samples: list[dict[str, np.ndarray]] = []
    ids: list[str] = []
    for row in train.itertuples(index=False):
        image = Image.open(crops_root / row.path).convert("RGB")
        tensor = transform(image).unsqueeze(0).numpy().astype(np.float32)
        samples.append({"input": tensor})
        ids.append(str(row.crop_id))
    return samples, ids


def run_onnx(path: Path, tensor: torch.Tensor) -> int:
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: tensor.numpy().astype(np.float32)})[0]
    return int(np.argmax(logits, axis=1)[0])


def consistency_check(
    model: torch.nn.Module, fp32: Path, int8: Path, crops_root: Path, calibration_ids: Path
) -> dict:
    """Una imagen de train conocida: misma clase en PyTorch, FP32 e INT8.

    La muestra es el **primer ID de `calibracion_ids.txt`** (fuente de verdad
    de la calibración), no el primer archivo de la carpeta: así la evidencia
    siempre proviene de los datos usados para cuantizar.
    """
    ids = [line.strip() for line in calibration_ids.read_text(encoding="utf-8").splitlines()]
    if not ids:
        raise ValueError(f"{calibration_ids} está vacío: no hay calibración registrada.")
    sample = crops_root / "images" / f"{ids[0]}.jpg"
    if not sample.is_file():
        raise FileNotFoundError(f"El recorte de calibración no existe: {sample}")
    transform = get_preprocessing_transforms("val", R02_CONFIG.image_size)
    tensor = transform(Image.open(sample).convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        pytorch_class = int(torch.argmax(model(tensor), dim=1).item())
    fp32_class = run_onnx(fp32, tensor)
    int8_class = run_onnx(int8, tensor)
    return {
        "sample": str(sample.relative_to(crops_root)),
        "calibration_source": str(calibration_ids),
        "pytorch_class": pytorch_class,
        "fp32_class": fp32_class,
        "int8_class": int8_class,
        "all_agree": pytorch_class == fp32_class == int8_class,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTorch -> ONNX FP32 -> ONNX INT8.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--crops-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True, help="modelos .onnx (fuera de Git)")
    parser.add_argument("--report-dir", type=Path, required=True, help="log e IDs de calibración")
    parser.add_argument("--opset", type=int, default=OPSET_DEFAULT)
    parser.add_argument(
        "--calib-limit",
        type=int,
        default=0,
        help="nº de recortes de train para calibrar (0 = todos)",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    fp32_path = args.out_dir / "model_fp32.onnx"
    int8_path = args.out_dir / "model_int8.onnx"

    model = load_model(args.checkpoint)
    export_fp32(model, fp32_path, args.opset)

    samples, calib_ids = calibration_samples(args.manifest, args.crops_root, args.calib_limit)
    quantize_static(
        model_input=str(fp32_path),
        model_output=str(int8_path),
        calibration_data_reader=TrainCalibrationReader(samples),
        quant_format=QuantFormat.QDQ,
        per_channel=True,
        weight_type=QuantType.QInt8,
        activation_type=QuantType.QUInt8,
    )

    (args.report_dir / "calibracion_ids.txt").write_text(
        "\n".join(calib_ids) + "\n", encoding="utf-8"
    )
    ids_sha256 = hashlib.sha256("\n".join(calib_ids).encode()).hexdigest()

    onnx.checker.check_model(onnx.load(str(fp32_path)))
    onnx.checker.check_model(onnx.load(str(int8_path)))
    consistency = consistency_check(
        model, fp32_path, int8_path, args.crops_root, args.report_dir / "calibracion_ids.txt"
    )

    log = {
        "checkpoint": {"path": str(args.checkpoint), "sha256": sha256_file(args.checkpoint)},
        "models": {
            "fp32": {
                "path": str(fp32_path),
                "sha256": sha256_file(fp32_path),
                "size_bytes": fp32_path.stat().st_size,
            },
            "int8": {
                "path": str(int8_path),
                "sha256": sha256_file(int8_path),
                "size_bytes": int8_path.stat().st_size,
            },
        },
        "input_shape": [1, 3, R02_CONFIG.image_size, R02_CONFIG.image_size],
        "opset": args.opset,
        "quantization": {
            "method": "static",
            "quant_format": "QDQ",
            "per_channel": True,
            "weight_type": "QInt8",
            "activation_type": "QUInt8",
            "calibration_split": "train",
            "calibration_samples": len(calib_ids),
            "calibration_ids_sha256": ids_sha256,
        },
        "versions": {
            "torch": torch.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
            "numpy": np.__version__,
        },
        "consistency_check": consistency,
    }
    (args.report_dir / "conversion_log.json").write_text(
        json.dumps(log, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
