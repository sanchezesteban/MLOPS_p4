"""Reporte de recursos antes/después (issue P4-08).

Calcula, a partir del benchmark de la Raspberry Pi (issue #11) y del registro
de conversión (issue #5):

- p50 y p95 de latencia para FP32 e INT8 (percentil recalculable: interpolación
  lineal de `numpy.percentile`, `method="linear"`);
- reducción de tamaño = 100 * (tamaño_fp32 - tamaño_int8) / tamaño_fp32;
- aceleración, solo cuando supera la variabilidad de las mediciones.

El CSV del benchmark debe tener las columnas `variant` (`fp32` | `int8`) y
`latency_ms` (preprocesamiento + inferencia, **sin** envío). Ver
`docs/p4/reporte-optimizacion.md`.

Uso (desde `app/`):

    uv run --locked --no-build python edge/resource_report.py \
        --conversion-log ../reports/p4/conversion_log.json \
        --benchmark ../reports/p4/benchmark.csv \
        --output ../reports/p4/resources.json

Sin `--benchmark` (o si el archivo no existe) el reporte sale con la parte de
tamaño y `latency = null`, para poder correrlo antes de que exista el
benchmark de la Pi.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

VARIANTS = ("fp32", "int8")
PERCENTILE_METHOD = "numpy.percentile con interpolación lineal (method='linear')"


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q, method="linear"))


def latency_stats(values: list[float]) -> dict:
    """Resumen recalculable de una muestra de latencias en milisegundos."""
    return {
        "samples": len(values),
        "min_ms": float(np.min(values)),
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "max_ms": float(np.max(values)),
        "mean_ms": float(np.mean(values)),
        "std_ms": float(np.std(values)),
    }


def size_reduction_percent(fp32_bytes: int, int8_bytes: int) -> float:
    """100 * (orig - opt) / orig, la reducción de tamaño queda en por ciento."""
    return 100.0 * (fp32_bytes - int8_bytes) / fp32_bytes


def read_benchmark(path: Path) -> dict[str, list[float]]:
    """Agrupa `latency_ms` por `variant` a partir del CSV de la Pi."""
    grouped: dict[str, list[float]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or {"variant", "latency_ms"} - set(reader.fieldnames):
            raise ValueError("El CSV debe tener las columnas 'variant' y 'latency_ms'.")
        for row in reader:
            variant = row["variant"].strip()
            if variant not in VARIANTS:
                raise ValueError(f"variant desconocido: {variant!r}")
            grouped[variant].append(float(row["latency_ms"]))
    return dict(grouped)


def speedup(fp32: dict, int8: dict) -> dict:
    """Aceleración FP32/INT8 con una prueba conservadora de significancia.

    El cociente solo se considera una aceleración real si la diferencia entre
    las variantes supera la variabilidad de las mediciones (la suma de sus
    desviaciones estándar); si no, se reporta como dentro del ruido.
    """
    result: dict = {"p50_ratio": fp32["p50_ms"] / int8["p50_ms"]}
    result["p95_ratio"] = fp32["p95_ms"] / int8["p95_ms"]
    spread = fp32["std_ms"] + int8["std_ms"]
    p50_diff = abs(fp32["p50_ms"] - int8["p50_ms"])
    result["spread_ms"] = spread
    result["significant"] = p50_diff > spread
    result["note"] = (
        "La diferencia entre FP32 e INT8 supera la variabilidad combinada."
        if result["significant"]
        else "La diferencia entre FP32 e INT8 cabe dentro de la variabilidad de las mediciones."
    )
    return result


def build_report(conversion_log: Path, benchmark: Path | None) -> dict:
    log = json.loads(conversion_log.read_text(encoding="utf-8"))
    fp32_bytes = int(log["models"]["fp32"]["size_bytes"])
    int8_bytes = int(log["models"]["int8"]["size_bytes"])

    report: dict = {
        "percentile_method": PERCENTILE_METHOD,
        "size": {
            "fp32_bytes": fp32_bytes,
            "int8_bytes": int8_bytes,
            "reduction_percent": size_reduction_percent(fp32_bytes, int8_bytes),
        },
        "latency": None,
        "speedup": None,
        "status": "parcial",
        "latency_note": "Pendiente del benchmark de la Pi (issue #11).",
    }

    if benchmark is not None and benchmark.is_file():
        grouped = read_benchmark(benchmark)
        missing = [variant for variant in VARIANTS if variant not in grouped]
        if missing:
            raise ValueError(f"Faltan mediciones para: {', '.join(missing)}.")
        latency = {variant: latency_stats(grouped[variant]) for variant in VARIANTS}
        report["latency"] = latency
        report["speedup"] = speedup(latency["fp32"], latency["int8"])
        report["status"] = "completo"
        report["latency_note"] = None
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Recursos antes/después (FP32 vs INT8).")
    parser.add_argument("--conversion-log", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(args.conversion_log, args.benchmark)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
