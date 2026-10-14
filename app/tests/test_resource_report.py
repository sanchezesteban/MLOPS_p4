"""Pruebas del reporte de recursos (P4-08): percentiles recalculables, reducción
de tamaño y significancia de la aceleración. No dependen del benchmark real de
la Pi; usan un CSV de ejemplo escrito en `tmp_path`.
"""

import json
from pathlib import Path

import pytest
from edge.resource_report import (
    build_report,
    latency_stats,
    read_benchmark,
    size_reduction_percent,
    speedup,
)


def write_conversion_log(path: Path, fp32_bytes: int = 1000, int8_bytes: int = 250) -> Path:
    path.write_text(
        json.dumps(
            {"models": {"fp32": {"size_bytes": fp32_bytes}, "int8": {"size_bytes": int8_bytes}}}
        ),
        encoding="utf-8",
    )
    return path


def write_benchmark(path: Path, fp32: list[float], int8: list[float]) -> Path:
    lines = ["variant,latency_ms"]
    lines += [f"fp32,{value}" for value in fp32]
    lines += [f"int8,{value}" for value in int8]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_latency_stats_usa_percentil_lineal():
    stats = latency_stats([10, 20, 30, 40, 50])
    assert stats["samples"] == 5
    assert stats["p50_ms"] == 30
    assert stats["p95_ms"] == 48
    assert stats["min_ms"] == 10
    assert stats["max_ms"] == 50


def test_reduccion_de_tamano():
    assert size_reduction_percent(100, 25) == 75.0
    assert size_reduction_percent(45224191, 11430716) == pytest.approx(74.72, abs=0.01)


def test_speedup_solo_significativa_si_supera_la_variabilidad():
    estable = speedup(
        {"p50_ms": 100, "p95_ms": 120, "std_ms": 2},
        {"p50_ms": 60, "p95_ms": 70, "std_ms": 2},
    )
    assert estable["significant"] is True
    assert estable["p50_ratio"] == pytest.approx(100 / 60)

    ruidosa = speedup(
        {"p50_ms": 100, "p95_ms": 120, "std_ms": 20},
        {"p50_ms": 90, "p95_ms": 110, "std_ms": 20},
    )
    assert ruidosa["significant"] is False


def test_read_benchmark_agrupa_por_variante(tmp_path):
    path = write_benchmark(tmp_path / "b.csv", [10, 20], [5, 6])
    grouped = read_benchmark(path)
    assert grouped == {"fp32": [10.0, 20.0], "int8": [5.0, 6.0]}


def test_read_benchmark_rechaza_encabezado_incorrecto(tmp_path):
    path = tmp_path / "b.csv"
    path.write_text("variant,ms\nfp32,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="latency_ms"):
        read_benchmark(path)


def test_build_report_sin_benchmark_es_parcial(tmp_path):
    log = write_conversion_log(tmp_path / "conversion_log.json")
    report = build_report(log, None)
    assert report["status"] == "parcial"
    assert report["latency"] is None
    assert report["speedup"] is None
    assert report["size"]["reduction_percent"] == 75.0


def test_build_report_con_benchmark_es_completo(tmp_path):
    log = write_conversion_log(tmp_path / "conversion_log.json", 1000, 250)
    benchmark = write_benchmark(tmp_path / "b.csv", fp32=[100] * 20, int8=[60] * 20)
    report = build_report(log, benchmark)
    assert report["status"] == "completo"
    assert report["latency"]["fp32"]["p50_ms"] == 100
    assert report["latency"]["int8"]["p50_ms"] == 60
    assert report["speedup"]["significant"] is True
