"""Bitácora de envío (`log.jsonl`): un registro por intento, en orden -- nunca
se reescribe ni se borra una línea, solo se agregan nuevas. El estado actual
de una captura es el de su línea más reciente (así el archivo sigue siendo
seguro de escribir aunque el programa se interrumpa a la mitad)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def append(log_path: Path, capture_id: str, send_status: str, send_error: str | None, send_ms: float | None) -> None:
    record = {
        "capture_id": capture_id,
        "logged_at": datetime.now(UTC).astimezone().isoformat(),
        "send_status": send_status,
        "send_error": send_error,
        "send_ms": send_ms,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def latest_status_by_capture(log_path: Path) -> dict[str, dict]:
    """La última línea de cada `capture_id`. Vacío si el log no existe todavía."""
    latest: dict[str, dict] = {}
    if not log_path.is_file():
        return latest
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            latest[record["capture_id"]] = record
    return latest


def failed_capture_ids(log_path: Path) -> list[str]:
    return [
        capture_id
        for capture_id, record in latest_status_by_capture(log_path).items()
        if record["send_status"] == "error"
    ]
