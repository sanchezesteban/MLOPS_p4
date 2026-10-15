"""Simulador de la Raspberry Pi para la ingesta (issue P4-16).

Envía eventos del contrato v1 a `POST /captures` firmados con SigV4 (la ruta usa
autorización AWS_IAM), igual que lo hará la Pi. Sirve para que el portal y la Pi
avancen sin esperarse y como referencia de cómo firmar la petición.

Uso (desde `app/`):

    uv run python -m edge_ingest.simulate --url https://<api>.execute-api.us-east-2.amazonaws.com \
        --profile mlops-p4-device --count 4

    # Reintento del mismo evento: la segunda respuesta debe ser 200 con "duplicate": true.
    uv run python -m edge_ingest.simulate --url … --profile … --count 1 --repeat 2

    # Una fotografía real en lugar de la imagen sintética.
    uv run python -m edge_ingest.simulate --url … --profile … --image foto.jpg --label dog
"""

import argparse
import base64
import io
import json
import random
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from PIL import Image, ImageDraw

# Identidad propia del simulador: sus capturas no se confunden con las de la Pi
# (`rpi-zero2w-01`) y se pueden limpiar antes de la entrega (`evidence.py cleanup`).
DEVICE_ID = "simulador-laptop"
MODEL_VERSION = "resnet18-p3-v1.0.0-int8"
# SHA-256 del ONNX INT8 publicado en reports/p4/conversion_log.json (#5).
MODEL_SHA256 = "58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb"
LOCAL_TZ = timezone(timedelta(hours=-6))
COLORS = {"cat": (230, 140, 40), "dog": (60, 110, 200)}


def synthetic_jpeg(label: str, capture_id: str) -> bytes:
    """JPEG 640x480 con la clase y el ID dibujados, fácil de reconocer en el portal."""
    image = Image.new("RGB", (640, 480), COLORS[label])
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 40, 560, 440), outline=(255, 255, 255), width=4)
    draw.text((100, 60), f"SIMULADOR - {label}", fill=(255, 255, 255))
    draw.text((100, 90), capture_id, fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def build_event(label: str, image: bytes | None, device_id: str = DEVICE_ID) -> dict:
    capture_id = str(uuid.uuid4())
    jpeg = image if image is not None else synthetic_jpeg(label, capture_id)
    return {
        "capture_id": capture_id,
        "captured_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "device_id": device_id,
        "model_version": MODEL_VERSION,
        "model_sha256": MODEL_SHA256,
        "predicted_class": label,
        "confidence": round(random.uniform(0.55, 0.99), 4),
        "latency_ms": round(random.uniform(250, 600), 1),
        "crop": {"x": 80, "y": 40, "w": 480, "h": 400},
        "image_b64": base64.b64encode(jpeg).decode("ascii"),
    }


def signed_post(url: str, body: bytes, session: boto3.Session, region: str) -> tuple[int, str]:
    request = AWSRequest(
        method="POST", url=url, data=body, headers={"Content-Type": "application/json"}
    )
    SigV4Auth(session.get_credentials(), "execute-api", region).add_auth(request)
    prepared = urllib.request.Request(
        url, data=body, headers=dict(request.headers.items()), method="POST"
    )
    try:
        with urllib.request.urlopen(prepared, timeout=15) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, f"sin conexión: {exc.reason}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula la Pi enviando capturas a AWS.")
    parser.add_argument("--url", required=True, help="URL base de la API (sin /captures)")
    parser.add_argument("--profile", default=None, help="perfil AWS con permiso POST /captures")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--count", type=int, default=1, help="capturas distintas a enviar")
    parser.add_argument("--repeat", type=int, default=1, help="envíos de cada captura (mismo ID)")
    parser.add_argument("--label", choices=["cat", "dog", "alternate"], default="alternate")
    parser.add_argument("--image", type=Path, default=None, help="JPEG real en lugar del sintético")
    parser.add_argument("--device-id", default=DEVICE_ID, help="device_id de los eventos")
    parser.add_argument("--log", type=Path, default=None, help="guarda cada resultado en JSONL")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    url = args.url.rstrip("/") + "/captures"
    image = args.image.read_bytes() if args.image else None

    for index in range(args.count):
        label = args.label if args.label != "alternate" else ("cat", "dog")[index % 2]
        event = build_event(label, image, args.device_id)
        body = json.dumps(event).encode("utf-8")
        for attempt in range(1, args.repeat + 1):
            started = time.perf_counter()
            status, text = signed_post(url, body, session, args.region)
            send_ms = round((time.perf_counter() - started) * 1000, 1)
            print(
                f"{event['capture_id']} {label} intento={attempt} -> {status} {text} ({send_ms} ms)"
            )
            if args.log:
                with args.log.open("a", encoding="utf-8") as handle:
                    record = {k: v for k, v in event.items() if k != "image_b64"}
                    record.update(attempt=attempt, status=status, response=text, send_ms=send_ms)
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
