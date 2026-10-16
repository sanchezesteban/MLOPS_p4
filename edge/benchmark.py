"""P4-11: benchmark FP32 vs. INT8 en la Raspberry Pi Zero 2W.

Mismo CSV que espera `resource_report.py` (P4-08, acordado con Uriel): un solo
archivo, una fila por medición, columnas `variant,repetition,warmup,latency_ms`.
10 corridas de calentamiento descartadas (marcadas `warmup=true`, no cuentan
como medición válida) + al menos 100 medidas por variante (`warmup=false`).

Misma entrada para las dos variantes (una imagen real de `validacion/`, no
aleatoria), mismo runtime (`onnxruntime`, `CPUExecutionProvider`) y mismos
hilos (los que onnxruntime usa por defecto en este proceso) -- solo cambia el
modelo. `latency_ms` es preprocesamiento + inferencia, igual que en `main.py`;
el envío (P4-12) no existe en este script, así que no hay nada que excluir ahí.

Si una variante falla (por ejemplo el .onnx no existe o no carga), el error
se guarda en `<out>_errors.json` con la configuración, y el benchmark sigue
con la otra variante en vez de abortar todo.

Uso (en la Pi, dentro de ~/edge):

    ~/edge-venv/bin/python benchmark.py \
        --image validacion/000005_000004.jpg \
        --fp32 models/model_fp32.onnx --int8 models/model_int8.onnx \
        --out benchmark.csv --warmup 10 --measure 100
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from infer import Model
from preprocess import to_model_input

CROP = {"x": 0, "y": 0, "w": 0, "h": 0}
IMAGE_SIZE = 128


def _cpu_temp_c() -> float | None:
    """`vcgencmd measure_temp` -> "temp=42.8'C" en Raspberry Pi OS."""
    try:
        out = subprocess.run(
            ["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=5, check=True
        )
        return float(out.stdout.strip().split("=")[1].split("'")[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _peak_rss_kb() -> int | None:
    """Memoria pico del proceso (`VmHWM`), opcional -- Linux únicamente."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _bench_variant(
    variant: str, model_path: Path, frame: np.ndarray, warmup: int, measure: int
) -> list[dict]:
    model = Model(model_path)
    rows: list[dict] = []
    for is_warmup, count in ((True, warmup), (False, measure)):
        for rep in range(1, count + 1):
            t0 = time.perf_counter()
            model_input = to_model_input(frame, CROP, IMAGE_SIZE)
            preprocess_ms = (time.perf_counter() - t0) * 1000
            _, _, infer_ms = model.predict(model_input)
            rows.append(
                {
                    "variant": variant,
                    "repetition": rep,
                    "warmup": "true" if is_warmup else "false",
                    "latency_ms": round(preprocess_ms + infer_ms, 3),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--fp32", required=True)
    parser.add_argument("--int8", required=True)
    parser.add_argument("--out", default="benchmark.csv")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--measure", type=int, default=100)
    args = parser.parse_args()

    frame = np.array(Image.open(args.image).convert("RGB"))

    print(f"onnxruntime {ort.__version__}, providers: {ort.get_available_providers()}")
    temp_before = _cpu_temp_c()
    print(f"temperatura CPU antes: {temp_before} C")

    rows: list[dict] = []
    errors: dict[str, str] = {}

    for variant, model_path in (("fp32", Path(args.fp32)), ("int8", Path(args.int8))):
        try:
            rows += _bench_variant(variant, model_path, frame, args.warmup, args.measure)
            print(f"{variant}: {args.warmup} de calentamiento + {args.measure} medidas, ok")
        except Exception as exc:  # noqa: BLE001 -- se registra y se sigue con la otra variante
            errors[variant] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {variant}: {errors[variant]}")

    temp_after = _cpu_temp_c()
    peak_rss_kb = _peak_rss_kb()
    print(f"temperatura CPU despues: {temp_after} C")
    print(f"pico de RSS (VmHWM): {peak_rss_kb} KB")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["variant", "repetition", "warmup", "latency_ms"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} filas escritas en {out_path}")

    conditions = {
        "image": args.image,
        "onnxruntime_version": ort.__version__,
        "providers": ort.get_available_providers(),
        "warmup_per_variant": args.warmup,
        "measure_per_variant": args.measure,
        "cpu_temp_before_c": temp_before,
        "cpu_temp_after_c": temp_after,
        "peak_rss_kb": peak_rss_kb,
        "errors": errors,
    }
    conditions_path = out_path.with_name(out_path.stem + "_conditions.json")
    conditions_path.write_text(json.dumps(conditions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"condiciones guardadas en {conditions_path}")


if __name__ == "__main__":
    main()
