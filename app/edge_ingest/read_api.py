"""API de lectura de capturas edge para el portal (issue P4-17, contrato del evento v1).

Lambda detrás de `GET /captures?limit=50` (API Gateway HTTP, sin firma para que el
navegador del portal la consulte; CORS limitado a los orígenes del portal). Lista las
capturas de la más reciente a la más antigua usando el índice `by_captured_at` y agrega
`image_url`: una URL firmada de S3 válida por 15 minutos.

Solo depende de la biblioteca estándar y de boto3 (incluido en el runtime de Lambda).
"""

import json
import logging
import os
from decimal import Decimal
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

INDEX_NAME = "by_captured_at"
GSI_PK = "capture"
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
URL_TTL_SECONDS = 15 * 60

# Campos que devuelve la API (contrato v1). `gsi_pk` y `captured_at_utc` son internos.
PUBLIC_FIELDS = (
    "capture_id",
    "captured_at",
    "received_at",
    "device_id",
    "model_version",
    "model_sha256",
    "predicted_class",
    "confidence",
    "latency_ms",
    "crop",
    "image_key",
)


class BadRequest(Exception):
    pass


def parse_limit(params: dict | None) -> int:
    raw = (params or {}).get("limit")
    if raw is None or raw == "":
        return DEFAULT_LIMIT
    try:
        limit = int(raw)
    except ValueError as exc:
        raise BadRequest("limit debe ser un entero") from exc
    if not 1 <= limit <= MAX_LIMIT:
        raise BadRequest(f"limit debe estar entre 1 y {MAX_LIMIT}")
    return limit


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _from_dynamo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(item) for item in value]
    return value


def to_public(item: dict, image_url: str) -> dict:
    public = {field: _from_dynamo(item.get(field)) for field in PUBLIC_FIELDS}
    # `confidence` y `latency_ms` son números del contrato aunque valgan 1 o 400 exactos.
    for field in ("confidence", "latency_ms"):
        if public[field] is not None:
            public[field] = float(public[field])
    public["image_url"] = image_url
    return public


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def list_captures(params: dict | None, *, s3, table, bucket: str) -> dict:
    """Lógica de la lectura, con clientes inyectados para probarla sin AWS."""
    try:
        limit = parse_limit(params)
    except BadRequest as exc:
        return _response(400, {"error": str(exc), "field": "limit"})

    result = table.query(
        IndexName=INDEX_NAME,
        KeyConditionExpression="gsi_pk = :pk",
        ExpressionAttributeValues={":pk": GSI_PK},
        ScanIndexForward=False,
        Limit=limit,
    )
    items = [
        to_public(
            item,
            s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": item["image_key"]},
                ExpiresIn=URL_TTL_SECONDS,
            ),
        )
        for item in result.get("Items", [])
    ]
    return _response(200, {"items": items})


_clients: dict[str, Any] = {}


def lambda_handler(event: dict, context: Any) -> dict:
    if not _clients:
        import boto3
        from botocore.config import Config

        region = os.environ.get("AWS_REGION", "us-east-2")
        # Endpoint regional y firma v4: la URL firmada funciona en el navegador sin redirecciones.
        _clients["s3"] = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
        _clients["table"] = boto3.resource("dynamodb").Table(os.environ["CAPTURES_TABLE"])

    try:
        return list_captures(
            event.get("queryStringParameters"),
            s3=_clients["s3"],
            table=_clients["table"],
            bucket=os.environ["CAPTURES_BUCKET"],
        )
    except Exception:
        logger.exception("falla interna en la lectura")
        return _response(500, {"error": "no se pudieron leer las capturas; intenta de nuevo"})
