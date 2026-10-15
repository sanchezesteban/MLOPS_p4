"""API de lectura de capturas edge (P4-17) con S3 y DynamoDB falsos."""

import json
from decimal import Decimal

import pytest
from edge_ingest import read_api


class FakeS3:
    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        assert operation == "get_object"
        assert ExpiresIn == 900
        return f"https://signed/{Params['Bucket']}/{Params['Key']}"


class FakeTable:
    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.last_query: dict = {}

    def query(self, **kwargs):
        self.last_query = kwargs
        ordered = sorted(self.items, key=lambda item: item["captured_at_utc"], reverse=True)
        return {"Items": ordered[: kwargs["Limit"]]}


def stored(capture_id: str, captured_at_utc: str, **overrides) -> dict:
    item = {
        "capture_id": capture_id,
        "captured_at": "2026-10-13T10:15:02-06:00",
        "captured_at_utc": captured_at_utc,
        "received_at": "2026-10-13T16:15:03.000Z",
        "device_id": "rpi-zero2w-01",
        "model_version": "resnet18-p3-v1.0.0-int8",
        "model_sha256": "a" * 64,
        "predicted_class": "dog",
        "confidence": Decimal("0.93"),
        "latency_ms": Decimal("412.7"),
        "crop": {"x": Decimal(80), "y": Decimal(40), "w": Decimal(480), "h": Decimal(400)},
        "image_key": f"captures/2026/10/13/{capture_id}.jpg",
        "gsi_pk": "capture",
    }
    item.update(overrides)
    return item


def call(params, items):
    table = FakeTable(items)
    response = read_api.list_captures(params, s3=FakeS3(), table=table, bucket="b")
    return response["statusCode"], json.loads(response["body"]), table, response


def test_lists_newest_first_with_contract_fields_and_signed_url():
    items = [
        stored("old", "2026-10-13T10:00:00.000Z"),
        stored("new", "2026-10-13T12:00:00.000Z"),
        stored("mid", "2026-10-13T11:00:00.000Z"),
    ]
    status, body, table, response = call(None, items)

    assert status == 200
    assert [item["capture_id"] for item in body["items"]] == ["new", "mid", "old"]
    assert table.last_query["IndexName"] == "by_captured_at"
    assert table.last_query["ScanIndexForward"] is False
    assert table.last_query["Limit"] == 50
    assert response["headers"]["Cache-Control"] == "no-store"

    first = body["items"][0]
    assert set(first) == {*read_api.PUBLIC_FIELDS, "image_url"}
    assert first["image_url"] == "https://signed/b/captures/2026/10/13/new.jpg"
    assert first["confidence"] == 0.93
    assert first["latency_ms"] == 412.7
    assert first["crop"] == {"x": 80, "y": 40, "w": 480, "h": 400}


def test_integer_valued_numbers_stay_numbers_and_null_crop_is_kept():
    item = stored("x", "2026-10-13T10:00:00.000Z", confidence=Decimal(1), crop=None)
    _, body, _, _ = call(None, [item])
    assert body["items"][0]["confidence"] == 1.0
    assert isinstance(body["items"][0]["confidence"], float)
    assert body["items"][0]["crop"] is None


def test_empty_table_returns_empty_list():
    status, body, _, _ = call({"limit": "5"}, [])
    assert (status, body) == (200, {"items": []})


def test_limit_is_applied():
    items = [stored(str(i), f"2026-10-13T10:00:{i:02d}.000Z") for i in range(10)]
    _, body, table, _ = call({"limit": "3"}, items)
    assert table.last_query["Limit"] == 3
    assert [item["capture_id"] for item in body["items"]] == ["9", "8", "7"]


@pytest.mark.parametrize("limit", ["0", "101", "abc", "-1"])
def test_invalid_limit_is_rejected(limit):
    status, body, _, _ = call({"limit": limit}, [])
    assert status == 400
    assert body["field"] == "limit"


def test_lambda_handler_reports_internal_errors(monkeypatch):
    monkeypatch.setenv("CAPTURES_BUCKET", "b")

    class BrokenTable:
        def query(self, **kwargs):
            raise RuntimeError("DynamoDB caído")

    monkeypatch.setattr(read_api, "_clients", {"s3": FakeS3(), "table": BrokenTable()})
    response = read_api.lambda_handler({"queryStringParameters": None}, None)
    assert response["statusCode"] == 500
    assert json.loads(response["body"])["error"]
