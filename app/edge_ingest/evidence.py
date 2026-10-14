"""Evidencia de AWS para la entrega y la evaluación (issue P4-19, rúbrica 4.2 y 6.3).

Consultas de **solo lectura** que el evaluador o el equipo ejecutan con su propio perfil:

    # Una captura: metadatos en DynamoDB + objeto en S3 (versión, tamaño, fecha).
    uv run python -m edge_ingest.evidence --profile mlops-p4 get <capture_id> [--download foto.jpg]

    # Todas las capturas, de la más reciente a la más antigua, a CSV y JSON.
    uv run python -m edge_ingest.evidence --profile mlops-p4 export --out ../evidencias/aws

Y una limpieza (requiere un perfil administrador) para quitar las capturas de prueba antes
de la entrega. Sin `--confirm` solo muestra qué borraría:

    uv run python -m edge_ingest.evidence --profile <admin> cleanup --device-id simulador-laptop
    uv run python -m edge_ingest.evidence --profile <admin> cleanup --device-id … --confirm
"""

import argparse
import csv
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3

REGION = "us-east-2"
TABLE = "mlops-p4-captures"
BUCKET = "mlops-p4-captures-595981034933"
INDEX_NAME = "by_captured_at"

CSV_FIELDS = (
    "capture_id",
    "captured_at",
    "captured_at_utc",
    "received_at",
    "device_id",
    "model_version",
    "model_sha256",
    "predicted_class",
    "confidence",
    "latency_ms",
    "crop_x",
    "crop_y",
    "crop_w",
    "crop_h",
    "image_key",
    "image_in_s3",
    "image_bytes",
    "image_version_id",
    "image_last_modified",
)


def plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    return value


def all_captures(table) -> list[dict]:
    """Todas las capturas del índice, de la más reciente a la más antigua (con paginación)."""
    items: list[dict] = []
    kwargs: dict[str, Any] = {
        "IndexName": INDEX_NAME,
        "KeyConditionExpression": "gsi_pk = :pk",
        "ExpressionAttributeValues": {":pk": "capture"},
        "ScanIndexForward": False,
    }
    while True:
        page = table.query(**kwargs)
        items.extend(plain(item) for item in page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def image_info(s3, bucket: str, key: str) -> dict:
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return {"image_in_s3": False}
        raise
    return {
        "image_in_s3": True,
        "image_bytes": head["ContentLength"],
        "image_version_id": head.get("VersionId"),
        "image_last_modified": head["LastModified"].isoformat(),
    }


def to_row(item: dict, info: dict) -> dict:
    crop = item.get("crop") or {}
    row = {field: item.get(field) for field in CSV_FIELDS}
    row.update({f"crop_{key}": crop.get(key) for key in ("x", "y", "w", "h")})
    row.update(info)
    return row


def export(table, s3, bucket: str, out_dir: Path) -> list[dict]:
    rows = [to_row(item, image_info(s3, bucket, item["image_key"])) for item in all_captures(table)]
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "eventos.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "eventos.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return rows


def summary(rows: list[dict]) -> dict:
    return {
        "eventos": len(rows),
        "por_clase": dict(Counter(row["predicted_class"] for row in rows)),
        "por_dispositivo": dict(Counter(row["device_id"] for row in rows)),
        "imagenes_faltantes": [row["capture_id"] for row in rows if not row["image_in_s3"]],
    }


def get_capture(table, s3, bucket: str, capture_id: str, download: Path | None) -> dict | None:
    item = table.get_item(Key={"capture_id": capture_id}, ConsistentRead=True).get("Item")
    if item is None:
        return None
    item = plain(item)
    result = {"dynamodb": item, "s3": image_info(s3, bucket, item["image_key"])}
    if download and result["s3"]["image_in_s3"]:
        s3.download_file(bucket, item["image_key"], str(download))
        result["s3"]["downloaded_to"] = str(download)
    return result


def cleanup(table, s3, bucket: str, device_id: str, confirm: bool) -> list[dict]:
    """Borra las capturas de `device_id` (metadatos + todas las versiones de la imagen)."""
    targets = [item for item in all_captures(table) if item["device_id"] == device_id]
    if not confirm:
        return targets
    for item in targets:
        versions = s3.list_object_versions(Bucket=bucket, Prefix=item["image_key"])
        for entry in versions.get("Versions", []) + versions.get("DeleteMarkers", []):
            if entry["Key"] == item["image_key"]:
                s3.delete_object(Bucket=bucket, Key=entry["Key"], VersionId=entry["VersionId"])
        table.delete_item(Key={"capture_id": item["capture_id"]})
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidencia de capturas en AWS (P4).")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--table", default=TABLE)
    parser.add_argument("--bucket", default=BUCKET)
    commands = parser.add_subparsers(dest="command", required=True)

    get = commands.add_parser("get", help="una captura por capture_id")
    get.add_argument("capture_id")
    get.add_argument("--download", type=Path, default=None, help="guarda la foto en este archivo")

    exp = commands.add_parser("export", help="todas las capturas a eventos.csv y eventos.json")
    exp.add_argument("--out", type=Path, default=Path("../evidencias/aws"))

    clean = commands.add_parser("cleanup", help="borra capturas de prueba de un device_id")
    clean.add_argument("--device-id", required=True)
    clean.add_argument("--confirm", action="store_true", help="sin esto solo lista")

    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = session.client("s3")
    table = session.resource("dynamodb").Table(args.table)

    if args.command == "get":
        result = get_capture(table, s3, args.bucket, args.capture_id, args.download)
        if result is None:
            print(f"no existe la captura {args.capture_id}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "export":
        rows = export(table, s3, args.bucket, args.out)
        print(json.dumps(summary(rows), indent=2, ensure_ascii=False))
        print(f"escrito: {args.out / 'eventos.csv'} y {args.out / 'eventos.json'}")
    else:
        targets = cleanup(table, s3, args.bucket, args.device_id, args.confirm)
        verb = "borradas" if args.confirm else "se borrarían (usa --confirm)"
        for item in targets:
            print(f"{item['capture_id']} {item['captured_at']} {item['predicted_class']}")
        print(f"{len(targets)} capturas de device_id={args.device_id} {verb}")


if __name__ == "__main__":
    main()
