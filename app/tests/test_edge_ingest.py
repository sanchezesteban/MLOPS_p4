"""Ingesta idempotente de capturas edge (P4-16) con S3 y DynamoDB falsos."""

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from edge_ingest import handler

NOW = datetime(2026, 10, 13, 16, 15, 3, tzinfo=UTC)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class ConditionalCheckFailed(Exception):
    def __init__(self) -> None:
        super().__init__("condición no cumplida")
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        assert ContentType == "image/jpeg"
        self.objects[f"{Bucket}/{Key}"] = Body


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.puts = 0

    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        item = self.items.get(Key["capture_id"])
        return {"Item": item} if item else {}

    def put_item(self, *, Item, ConditionExpression):
        assert ConditionExpression == "attribute_not_exists(capture_id)"
        self.puts += 1
        if Item["capture_id"] in self.items:
            raise ConditionalCheckFailed()
        self.items[Item["capture_id"]] = Item


def make_event(**overrides) -> dict:
    event = {
        "capture_id": str(uuid.uuid4()),
        "captured_at": "2026-10-13T19:15:02-06:00",
        "device_id": "rpi-zero2w-01",
        "model_version": "resnet18-p3-v1.0.0-int8",
        "model_sha256": "a" * 64,
        "predicted_class": "dog",
        "confidence": 0.93,
        "latency_ms": 412.7,
        "crop": {"x": 80, "y": 40, "w": 480, "h": 400},
        "image_b64": base64.b64encode(JPEG).decode(),
    }
    event.update(overrides)
    return event


def send(event, s3=None, table=None):
    s3 = s3 if s3 is not None else FakeS3()
    table = table if table is not None else FakeTable()
    body = event if isinstance(event, str) else json.dumps(event)
    response = handler.ingest(body, s3=s3, table=table, bucket="captures-bucket", now=NOW)
    return response["statusCode"], json.loads(response["body"]), s3, table


def test_new_capture_stores_image_and_metadata_and_returns_201():
    event = make_event()
    status, body, s3, table = send(event)

    assert status == 201
    # captured_at -06:00 a las 19:15 es el día 14 en UTC: la clave usa la fecha UTC.
    key = f"captures/2026/10/14/{event['capture_id']}.jpg"
    assert body == {
        "capture_id": event["capture_id"],
        "received_at": "2026-10-13T16:15:03.000Z",
        "image_key": key,
        "duplicate": False,
    }
    assert s3.objects == {f"captures-bucket/{key}": JPEG}

    item = table.items[event["capture_id"]]
    assert item["captured_at"] == "2026-10-13T19:15:02-06:00"
    assert item["captured_at_utc"] == "2026-10-14T01:15:02.000Z"
    assert item["gsi_pk"] == "capture"
    assert item["confidence"] == Decimal("0.93")
    assert item["crop"] == {"x": 80, "y": 40, "w": 480, "h": 400}
    assert "image_b64" not in item


def test_resending_the_same_capture_id_does_not_duplicate():
    event = make_event()
    _, first, s3, table = send(event)
    status, second, s3, table = send(event, s3, table)

    assert status == 200
    assert second == {**first, "duplicate": True}
    assert len(table.items) == 1
    assert table.puts == 1
    assert len(s3.objects) == 1


def test_concurrent_duplicate_returns_the_first_record():
    event = make_event()
    table = FakeTable()
    winner = {"capture_id": event["capture_id"], "received_at": "X", "image_key": "K"}

    original_get = table.get_item
    calls = {"n": 0}

    def get_item(**kwargs):
        # La primera lectura no ve el registro; entre lectura y escritura llega otro envío.
        calls["n"] += 1
        if calls["n"] == 1:
            table.items[event["capture_id"]] = winner
            return {}
        return original_get(**kwargs)

    table.get_item = get_item
    status, body, _, _ = send(event, table=table)

    assert status == 200
    assert body == {
        "capture_id": event["capture_id"],
        "received_at": "X",
        "image_key": "K",
        "duplicate": True,
    }
    assert table.items[event["capture_id"]] is winner


def test_crop_may_be_null():
    status, _, _, table = send(make_event(crop=None))
    assert status == 201
    assert next(iter(table.items.values()))["crop"] is None


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"capture_id": "no-es-uuid"}, "capture_id"),
        ({"capture_id": str(uuid.uuid1())}, "capture_id"),
        ({"captured_at": "2026-10-13T10:15:02"}, "captured_at"),
        ({"captured_at": "ayer"}, "captured_at"),
        ({"device_id": ""}, "device_id"),
        ({"model_sha256": "ABC"}, "model_sha256"),
        ({"predicted_class": "bird"}, "predicted_class"),
        ({"confidence": 1.01}, "confidence"),
        ({"confidence": -0.1}, "confidence"),
        ({"confidence": True}, "confidence"),
        ({"confidence": "0.9"}, "confidence"),
        ({"latency_ms": -1}, "latency_ms"),
        ({"crop": {"x": 0, "y": 0, "w": 0, "h": 10}}, "crop"),
        ({"crop": {"x": 0, "y": 0}}, "crop"),
        ({"image_b64": "%%%"}, "image_b64"),
        ({"image_b64": base64.b64encode(b"PNG...").decode()}, "image_b64"),
        (
            {"image_b64": base64.b64encode(JPEG + b"\x00" * handler.MAX_IMAGE_BYTES).decode()},
            "image_b64",
        ),
        ({"extra": 1}, "extra"),
    ],
)
def test_invalid_fields_are_rejected_with_400_and_nothing_is_written(overrides, field):
    status, body, s3, table = send(make_event(**overrides))

    assert status == 400
    assert body["field"] == field
    assert body["error"]
    assert s3.objects == {}
    assert table.items == {}


def test_missing_field_is_named():
    event = make_event()
    del event["model_version"]
    status, body, _, _ = send(event)
    assert (status, body["field"]) == (400, "model_version")


def test_body_that_is_not_json_is_rejected():
    status, body, _, _ = send("{no json")
    assert (status, body["field"]) == (400, "body")


def test_lambda_handler_decodes_base64_body_and_reports_internal_errors(monkeypatch):
    monkeypatch.setenv("CAPTURES_BUCKET", "captures-bucket")

    class BrokenS3:
        def put_object(self, **kwargs):
            raise RuntimeError("S3 caído")

    monkeypatch.setattr(handler, "_clients", {"s3": BrokenS3(), "table": FakeTable()})
    raw = json.dumps(make_event()).encode()
    response = handler.lambda_handler(
        {"body": base64.b64encode(raw).decode(), "isBase64Encoded": True}, None
    )

    assert response["statusCode"] == 500
    assert "mismo capture_id" in json.loads(response["body"])["error"]
