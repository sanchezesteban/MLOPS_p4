"""P4-09: captura + inferencia local en la Pi. P4-12: envío a AWS.

Por tecla o intervalo configurable. Cada captura guarda un JPEG + un JSON
local en el `output_dir` con los campos del contrato del evento
(docs/p4/contrato-evento.md) que ya se conocen en el dispositivo;
`received_at` e `image_key` los agrega AWS al recibir, no viven aquí.

La clasificación NUNCA depende de la red: si `api_url` está configurado se
intenta mandar cada captura (P4-12), pero un fallo de envío (sin red, 5xx,
lo que sea) solo se registra en `log.jsonl` -- no detiene ni hace fallar la
captura/clasificación siguiente.

Tampoco un fallo real de captura (p. ej. un glitch transitorio de la cámara
USB) debe tumbar la operación continua (P4-13, "5 minutos sin caídas"): en
modo intervalo/tecla, una excepción de una sola vuelta se registra en
`errors.log` y el programa sigue con la siguiente captura, en vez de morir
por completo. Antes de esta corrección el `while True` solo atrapaba
`KeyboardInterrupt` -- cualquier otra excepción tumbaba todo el proceso sin
dejar rastro; es la sospecha más probable de por qué una corrida de P4-13 se
cortó sola a los ~2 minutos sin que quedara ningún traceback guardado.

Uso:
    python main.py --config config.json             # modo continuo (tecla/intervalo)
    python main.py --config config.json --once       # una sola captura y termina
    python main.py --config config.json --retry <id> # reintenta una captura por su ID
    python main.py --config config.json --retry-failed  # reintenta todas las que quedaron en error
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

import capture_log
from frame_source import build_frame_source
from infer import Model
from preprocess import to_model_input
from send import send_event


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _log_capture_error(errors_path: Path, exc: Exception) -> None:
    """Una captura fallida se registra y se sigue -- nunca debe perderse en
    silencio como pasaba antes (ver docstring del módulo)."""
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).astimezone().isoformat()
    with errors_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {type(exc).__name__}: {exc}\n")
        handle.write(traceback.format_exc())
        handle.write("\n")
    print(f"ERROR en esta captura (se sigue con la siguiente): {type(exc).__name__}: {exc}")


def _crop_or_null(crop: dict) -> dict | None:
    """El contrato del evento (docs/p4/contrato-evento.md) pide `w`/`h` > 0 o
    `null` -- la ingesta de Ikram rechaza {"x":0,"y":0,"w":0,"h":0} con 400."""
    if crop.get("w", 0) <= 0 or crop.get("h", 0) <= 0:
        return None
    return crop


def _maybe_send(config: dict, output_dir: Path, event: dict, image_bytes: bytes) -> dict | None:
    """Si hay `api_url` configurada, intenta mandar la captura. Registra
    `pendiente` ANTES de intentar (para que `log.jsonl` nunca mienta sobre
    una captura que sí se tomó pero cuyo envío se interrumpió a medio
    camino) y el resultado real después. Nunca lanza."""
    if not config.get("api_url"):
        return None
    log_path = output_dir / config.get("log_path", "log.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    capture_log.append(log_path, event["capture_id"], "pendiente", None, None)
    result = send_event(event, image_bytes, config)
    capture_log.append(
        log_path, event["capture_id"], result["send_status"], result["send_error"], result["send_ms"]
    )
    return result


def _run_once(config: dict, model: Model, frame_source, output_dir: Path) -> dict:
    # El cronómetro arranca DESPUÉS de leer la cámara: `latency_ms` es solo
    # preprocesamiento + inferencia, como pide el contrato -- leer la cámara
    # no cuenta (con cámara real eso agrega ~300ms que no son del modelo).
    frame = frame_source.read()
    t0 = time.perf_counter()
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
        "crop": _crop_or_null(config["crop"]),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    jpg_path = output_dir / f"{capture_id}.jpg"
    Image.fromarray(frame).save(jpg_path, format="JPEG")
    (output_dir / f"{capture_id}.json").write_text(
        json.dumps(event, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    send_result = _maybe_send(config, output_dir, event, jpg_path.read_bytes())
    return event, send_result


def _format_event(event: dict, send_result: dict | None) -> str:
    base = (
        f"[{event['capture_id'][:8]}] {event['predicted_class']} "
        f"(confianza {event['confidence']:.2f}, {event['latency_ms']:.1f} ms)"
    )
    if send_result is None:
        return base
    if send_result["send_status"] == "enviado":
        return f"{base} -- enviado ({send_result['send_ms']} ms)"
    return f"{base} -- ERROR al enviar: {send_result['send_error']}"


def _retry_one(config: dict, output_dir: Path, capture_id: str) -> None:
    """Reintenta UNA captura ya guardada localmente -- no toma una foto
    nueva, reusa el mismo `capture_id` (así AWS la reconoce como
    reintento/duplicado, no como un evento distinto)."""
    event_path = output_dir / f"{capture_id}.json"
    jpg_path = output_dir / f"{capture_id}.jpg"
    if not event_path.is_file() or not jpg_path.is_file():
        print(f"[{capture_id[:8]}] no se encontró localmente, no se puede reintentar")
        return
    event = json.loads(event_path.read_text(encoding="utf-8"))
    result = _maybe_send(config, output_dir, event, jpg_path.read_bytes())
    print(_format_event(event, result))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once", action="store_true", help="Una sola captura y termina")
    parser.add_argument("--retry", metavar="CAPTURE_ID", help="Reintenta una captura por su ID")
    parser.add_argument(
        "--retry-failed", action="store_true", help="Reintenta todas las capturas en estado error"
    )
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    output_dir = Path(config.get("output_dir", "capturas"))

    if args.retry:
        _retry_one(config, output_dir, args.retry)
        return
    if args.retry_failed:
        log_path = output_dir / config.get("log_path", "log.jsonl")
        failed = capture_log.failed_capture_ids(log_path)
        if not failed:
            print("No hay capturas en estado error.")
            return
        print(f"Reintentando {len(failed)} captura(s) en error...")
        for capture_id in failed:
            _retry_one(config, output_dir, capture_id)
        return

    model = Model(config["model_path"])
    frame_source = build_frame_source(config)

    print(f"Modelo cargado: {config['model_path']} (sha256 {model.sha256[:12]}...)")
    print(f"Fuente de frame: {config.get('frame_source', 'stub')}")

    try:
        if args.once:
            event, send_result = _run_once(config, model, frame_source, output_dir)
            print(_format_event(event, send_result))
            return

        mode = config.get("capture_mode", "interval")
        interval = config.get("capture_interval_seconds", 5)
        errors_path = output_dir / "errors.log"
        print(f"Modo: {mode} (Ctrl+C para salir)")
        while True:
            if mode == "key":
                input("Presiona Enter para capturar...")
            try:
                event, send_result = _run_once(config, model, frame_source, output_dir)
                print(_format_event(event, send_result))
            except Exception as exc:  # noqa: BLE001 -- una captura fallida no debe tumbar la operación continua
                _log_capture_error(errors_path, exc)
            if mode == "interval":
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nDetenido por el usuario.")
    finally:
        frame_source.close()


if __name__ == "__main__":
    main()
