"""Evidencia de AWS (P4-19) con S3 y DynamoDB falsos."""

import csv
import json
from datetime import UTC, datetime
from decimal import Decimal

from edge_ingest import evidence


class NotFound(Exception):
    def __init__(self) -> None:
        super().__init__("404")
        self.response = {"Error": {"Code": "404"}}


class FakeS3:
    def __init__(self, keys: set[str]) -> None:
        self.keys = set(keys)
        self.deleted: list[tuple[str, str]] = []

    def head_object(self, *, Bucket, Key):
        if Key not in self.keys:
            raise NotFound()
        return {
            "ContentLength": 123,
            "VersionId": f"v-{Key}",
            "LastModified": datetime(2026, 10, 14, tzinfo=UTC),
        }

    def list_object_versions(self, *, Bucket, Prefix):
        return {"Versions": [{"Key": Prefix, "VersionId": f"v-{Prefix}"}]}

    def delete_object(self, *, Bucket, Key, VersionId):
        self.deleted.append((Key, VersionId))
        self.keys.discard(Key)


class FakeTable:
    """Devuelve el índice en dos páginas para probar la paginación."""

    def __init__(self, items: list[dict]) -> None:
        self.items = {item["capture_id"]: item for item in items}

    def query(self, **kwargs):
        ordered = sorted(self.items.values(), key=lambda i: i["captured_at_utc"], reverse=True)
        start = kwargs.get("ExclusiveStartKey", {}).get("offset", 0)
        page = ordered[start : start + 2]
        result = {"Items": page}
        if start + 2 < len(ordered):
            result["LastEvaluatedKey"] = {"offset": start + 2}
        return result

    def get_item(self, *, Key, ConsistentRead):
        item = self.items.get(Key["capture_id"])
        return {"Item": item} if item else {}

    def delete_item(self, *, Key):
        del self.items[Key["capture_id"]]


def item(capture_id: str, minute: int, device: str = "rpi-zero2w-01", label: str = "cat"):
    return {
        "capture_id": capture_id,
        "captured_at": f"2026-10-13T22:{minute:02d}:00-06:00",
        "captured_at_utc": f"2026-10-14T04:{minute:02d}:00.000Z",
        "received_at": f"2026-10-14T04:{minute:02d}:01.000Z",
        "device_id": device,
        "model_version": "resnet18-p3-v1.0.0-int8",
        "model_sha256": "a" * 64,
        "predicted_class": label,
        "confidence": Decimal("0.9"),
        "latency_ms": Decimal("400"),
        "crop": {"x": Decimal(1), "y": Decimal(2), "w": Decimal(3), "h": Decimal(4)},
        "image_key": f"captures/2026/10/14/{capture_id}.jpg",
        "gsi_pk": "capture",
    }


def test_export_writes_every_capture_newest_first_and_flags_missing_images(tmp_path):
    items = [item("a", 1), item("b", 2, label="dog"), item("c", 3), item("d", 4, label="dog")]
    s3 = FakeS3({i["image_key"] for i in items if i["capture_id"] != "b"})

    rows = evidence.export(FakeTable(items), s3, "bucket", tmp_path)

    with (tmp_path / "eventos.csv").open(encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert [row["capture_id"] for row in written] == ["d", "c", "b", "a"]
    assert written[0]["crop_w"] == "3"
    assert written[0]["confidence"] == "0.9"
    assert written[0]["image_version_id"] == "v-captures/2026/10/14/d.jpg"
    assert json.loads((tmp_path / "eventos.json").read_text(encoding="utf-8")) == rows
    assert evidence.summary(rows) == {
        "eventos": 4,
        "por_clase": {"dog": 2, "cat": 2},
        "por_dispositivo": {"rpi-zero2w-01": 4},
        "imagenes_faltantes": ["b"],
    }


def test_get_returns_metadata_and_s3_object_or_none():
    table = FakeTable([item("a", 1)])
    s3 = FakeS3({"captures/2026/10/14/a.jpg"})

    result = evidence.get_capture(table, s3, "bucket", "a", None)
    assert result["dynamodb"]["confidence"] == 0.9
    assert result["s3"]["image_in_s3"] is True
    assert evidence.get_capture(table, s3, "bucket", "zzz", None) is None


def test_cleanup_is_a_dry_run_unless_confirmed_and_only_touches_the_device():
    items = [
        item("pi", 1),
        item("sim1", 2, device="simulador-laptop"),
        item("sim2", 3, "simulador-laptop"),
    ]
    table = FakeTable(items)
    s3 = FakeS3({i["image_key"] for i in items})

    listed = evidence.cleanup(table, s3, "bucket", "simulador-laptop", confirm=False)
    assert {i["capture_id"] for i in listed} == {"sim1", "sim2"}
    assert set(table.items) == {"pi", "sim1", "sim2"}
    assert s3.deleted == []

    evidence.cleanup(table, s3, "bucket", "simulador-laptop", confirm=True)
    assert set(table.items) == {"pi"}
    assert s3.keys == {"captures/2026/10/14/pi.jpg"}
