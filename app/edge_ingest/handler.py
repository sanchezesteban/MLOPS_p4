"""Ingesta idempotente de capturas edge (issue P4-16, contrato del evento v1).

Lambda detrás de `POST /captures` (API Gateway HTTP, autorización AWS_IAM). Valida el
evento, guarda la fotografía en S3 y los metadatos en DynamoDB con escritura condicional
por `capture_id`: reenviar el mismo ID responde `200` con `"duplicate": true` y no crea
ni sobrescribe nada (rúbrica 4.1 a 4.3).

Solo depende de la biblioteca estándar y de boto3 (incluido en el runtime de Lambda), así
que el zip de despliegue es este único archivo.

Respuestas (docs/p4/contrato-evento.md):
- 201: evento nuevo guardado.
- 200: el `capture_id` ya existía; no se duplicó.
- 400: campo faltante o inválido; el cuerpo dice cuál.
- 500: falla interna; la Pi reintenta con el mismo `capture_id`.
"""

import base64
import binascii
import json
import logging
import math
import os
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CLASSES = {"cat", "dog"}
MAX_IMAGE_BYTES = 1024 * 1024
JPEG_MAGIC = b"\xff\xd8\xff"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GSI_PK = "capture"

REQUIRED_FIELDS = (
    "capture_id",
    "captured_at",
    "device_id",
    "model_version",
    "model_sha256",
    "predicted_class",
    "confidence",
    "latency_ms",
    "crop",
    "image_b64",
)
CROP_FIELDS = ("x", "y", "w", "h")


class ValidationError(Exception):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _non_empty_str(event: dict, field: str, max_len: int = 128) -> str:
    value = event[field]
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ValidationError(field, f"debe ser texto no vacío de hasta {max_len} caracteres")
    return value


def _parse_captured_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValidationError("captured_at", "debe ser texto ISO-8601")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("captured_at", "no es una fecha ISO-8601 válida") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("captured_at", "debe incluir zona horaria (ej. -06:00 o Z)")
    return parsed


def _parse_crop(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(CROP_FIELDS):
        raise ValidationError("crop", "debe ser null o un objeto con x, y, w, h")
    for key in CROP_FIELDS:
        number = value[key]
        if not isinstance(number, int) or isinstance(number, bool) or number < 0:
            raise ValidationError("crop", f"crop.{key} debe ser un entero >= 0")
    if value["w"] == 0 or value["h"] == 0:
        raise ValidationError("crop", "crop.w y crop.h deben ser mayores que 0")
    return {key: value[key] for key in CROP_FIELDS}


def _decode_image(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValidationError("image_b64", "debe ser un JPEG codificado en base64")
    try:
        image = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("image_b64", "no es base64 válido") from exc
    if len(image) > MAX_IMAGE_BYTES:
        raise ValidationError("image_b64", "la imagen supera 1 MB antes de codificar")
    if not image.startswith(JPEG_MAGIC):
        raise ValidationError("image_b64", "la imagen no es JPEG")
    return image


def validate(event: Any) -> tuple[dict, bytes, datetime]:
    """Devuelve (metadatos normalizados, bytes del JPEG, captured_at con zona)."""
    if not isinstance(event, dict):
        raise ValidationError("body", "el cuerpo debe ser un objeto JSON")
    missing = [field for field in REQUIRED_FIELDS if field not in event]
    if missing:
        raise ValidationError(missing[0], f"falta el campo {missing[0]}")
    unknown = sorted(set(event) - set(REQUIRED_FIELDS))
    if unknown:
        raise ValidationError(unknown[0], f"campo no definido en el contrato v1: {unknown[0]}")

    capture_id = event["capture_id"]
    try:
        parsed_id = uuid.UUID(capture_id) if isinstance(capture_id, str) else None
    except ValueError:
        parsed_id = None
    if parsed_id is None or parsed_id.version != 4 or str(parsed_id) != capture_id.lower():
        raise ValidationError("capture_id", "debe ser un UUID v4")

    captured_at = _parse_captured_at(event["captured_at"])

    model_sha256 = event["model_sha256"]
    if not isinstance(model_sha256, str) or not SHA256_RE.match(model_sha256):
        raise ValidationError("model_sha256", "debe ser un SHA-256 de 64 caracteres hex minúsculos")

    if event["predicted_class"] not in CLASSES:
        raise ValidationError("predicted_class", "debe ser 'cat' o 'dog'")

    confidence = event["confidence"]
    if not _is_number(confidence) or not 0 <= confidence <= 1:
        raise ValidationError("confidence", "debe ser un número entre 0 y 1")

    latency_ms = event["latency_ms"]
    if not _is_number(latency_ms) or latency_ms < 0:
        raise ValidationError("latency_ms", "debe ser un número >= 0")

    metadata = {
        "capture_id": str(parsed_id),
        "captured_at": event["captured_at"],
        "device_id": _non_empty_str(event, "device_id"),
        "model_version": _non_empty_str(event, "model_version"),
        "model_sha256": model_sha256,
        "predicted_class": event["predicted_class"],
        "confidence": confidence,
        "latency_ms": latency_ms,
        "crop": _parse_crop(event["crop"]),
    }
    return metadata, _decode_image(event["image_b64"]), captured_at


def image_key_for(capture_id: str, captured_at: datetime) -> str:
    """Clave determinista: un reintento escribe exactamente el mismo objeto."""
    day = captured_at.astimezone(UTC)
    return f"captures/{day:%Y/%m/%d}/{capture_id}.jpg"


def _utc_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamo(item) for key, item in value.items()}
    return value


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _is_conditional_failure(exc: Exception) -> bool:
    error = getattr(exc, "response", {}).get("Error", {})
    return error.get("Code") == "ConditionalCheckFailedException"


def _duplicate(item: dict) -> dict:
    return _response(
        200,
        {
            "capture_id": item["capture_id"],
            "received_at": item["received_at"],
            "image_key": item["image_key"],
            "duplicate": True,
        },
    )


def ingest(raw_body: str | None, *, s3, table, bucket: str, now: datetime) -> dict:
    """Lógica de la ingesta, con clientes inyectados para probarla sin AWS."""
    try:
        event = json.loads(raw_body or "")
    except json.JSONDecodeError:
        return _response(400, {"error": "el cuerpo no es JSON válido", "field": "body"})

    try:
        metadata, image, captured_at = validate(event)
    except ValidationError as exc:
        return _response(400, {"error": exc.message, "field": exc.field})

    capture_id = metadata["capture_id"]
    existing = table.get_item(Key={"capture_id": capture_id}, ConsistentRead=True).get("Item")
    if existing:
        logger.info("duplicado capture_id=%s", capture_id)
        return _duplicate(existing)

    image_key = image_key_for(capture_id, captured_at)
    item = {
        **metadata,
        "captured_at_utc": _utc_iso(captured_at),
        "received_at": _utc_iso(now),
        "image_key": image_key,
        "gsi_pk": GSI_PK,
    }

    # Primero la imagen: si DynamoDB falla después, el reintento reescribe la misma clave
    # y no queda un registro apuntando a una imagen inexistente.
    s3.put_object(Bucket=bucket, Key=image_key, Body=image, ContentType="image/jpeg")
    try:
        table.put_item(
            Item=_to_dynamo(item), ConditionExpression="attribute_not_exists(capture_id)"
        )
    except Exception as exc:
        if not _is_conditional_failure(exc):
            raise
        # Carrera entre dos envíos simultáneos del mismo ID: gana el primero.
        winner = table.get_item(Key={"capture_id": capture_id}, ConsistentRead=True)["Item"]
        return _duplicate(winner)

    logger.info("guardado capture_id=%s key=%s", capture_id, image_key)
    return _response(
        201,
        {
            "capture_id": capture_id,
            "received_at": item["received_at"],
            "image_key": image_key,
            "duplicate": False,
        },
    )


_clients: dict[str, Any] = {}


def lambda_handler(event: dict, context: Any) -> dict:
    if not _clients:
        import boto3

        _clients["s3"] = boto3.client("s3")
        _clients["table"] = boto3.resource("dynamodb").Table(os.environ["CAPTURES_TABLE"])

    body = event.get("body")
    if body is not None and event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        return ingest(
            body,
            s3=_clients["s3"],
            table=_clients["table"],
            bucket=os.environ["CAPTURES_BUCKET"],
            now=datetime.now(UTC),
        )
    except Exception:
        logger.exception("falla interna en la ingesta")
        return _response(500, {"error": "falla interna; reintenta con el mismo capture_id"})
