"""P4-09: captura + inferencia local en la Pi.

Por tecla o intervalo configurable, sin red (el envío a AWS es P4-12, aparte).
Cada captura guarda un JPEG + un JSON local en el `output_dir` con los campos
del contrato del evento (docs/p4/contrato-evento.md) que ya se conocen en el
dispositivo; `received_at` e `image_key` los agrega AWS al recibir, no viven
aquí.

Uso:
    python main.py --config config.json            # modo continuo (tecla/intervalo)
    python main.py --config config.json --once      # una sola captura y termina
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from frame_source import build_frame_source
from infer import Model
from preprocess import to_model_input


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_once(config: dict, model: Model, frame_source, output_dir: Path) -> dict:
    t0 = time.perf_counter()
    frame = frame_source.read()
    model_input = to_model_input(frame, config["crop"], config.get("image_size", 128))
    preprocess_ms = (time.perf_counter() - t0) * 1000

    predicted, confidence, infer_ms = model.predict(model_input)
    classes = config["classes"]

    capture_id = str(uuid.uuid4())
    captured_at = datetime.now(UTC).astimezone().isoformat()

    event = {
        "capture_id": capture_id,
        "captured_at": captured_at,
        "device_id": config["device_id"],
        "model_version": config["model_version"],
        "model_sha256": model.sha256,
        "predicted_class": classes[str(predicted)],
        "confidence": round(confidence, 4),
        "latency_ms": round(preprocess_ms + infer_ms, 2),
        "crop": config["crop"],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame).save(output_dir / f"{capture_id}.jpg", format="JPEG")
    (output_dir / f"{capture_id}.json").write_text(
        json.dumps(event, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return event


def _format_event(event: dict) -> str:
    return (
        f"[{event['capture_id'][:8]}] {event['predicted_class']} "
        f"(confianza {event['confidence']:.2f}, {event['latency_ms']:.1f} ms)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once", action="store_true", help="Una sola captura y termina")
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    model = Model(config["model_path"])
    frame_source = build_frame_source(config)
    output_dir = Path(config.get("output_dir", "capturas"))

    print(f"Modelo cargado: {config['model_path']} (sha256 {model.sha256[:12]}...)")
    print(f"Fuente de frame: {config.get('frame_source', 'stub')}")

    try:
        if args.once:
            print(_format_event(_run_once(config, model, frame_source, output_dir)))
            return

        mode = config.get("capture_mode", "interval")
        interval = config.get("capture_interval_seconds", 5)
        print(f"Modo: {mode} (Ctrl+C para salir)")
        while True:
            if mode == "key":
                input("Presiona Enter para capturar...")
            print(_format_event(_run_once(config, model, frame_source, output_dir)))
            if mode == "interval":
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nDetenido por el usuario.")
    finally:
        frame_source.close()


if __name__ == "__main__":
    main()
