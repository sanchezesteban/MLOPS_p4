"""P4-12: envío de capturas a AWS, firmado con SigV4.

Misma lógica de firma que `app/edge_ingest/simulate.py` (el simulador de Ikram
para #16), pero para el dispositivo real -- no están acopladas, cada una vive
en su propio codebase (`edge/` corre en la Pi, `app/edge_ingest/` es
Lambda/herramientas de desarrollo).

`201` (creado) y `200` (reintento del mismo `capture_id`, ya existía --
`duplicate: true`) cuentan como `enviado`. Cualquier otra respuesta HTTP, o no
tener red, es `error` -- el texto en `send_error` trae el código real (`400`,
`502`, `sin conexión: ...`) para que quien revise `log.jsonl` decida si vale
la pena reintentar (un `400` suele ser el propio evento mal formado, no se va
a arreglar solo con reintentar; un `5xx` o la falta de red sí son candidatos
naturales a `--retry`).
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

_OK_STATUSES = (200, 201)


def _signed_post(url: str, body: bytes, profile: str, region: str, timeout_s: float) -> tuple[int, str]:
    session = boto3.Session(profile_name=profile, region_name=region)
    request = AWSRequest(
        method="POST", url=url, data=body, headers={"Content-Type": "application/json"}
    )
    SigV4Auth(session.get_credentials(), "execute-api", region).add_auth(request)
    prepared = urllib.request.Request(
        url, data=body, headers=dict(request.headers.items()), method="POST"
    )
    try:
        with urllib.request.urlopen(prepared, timeout=timeout_s) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, f"sin conexión: {exc.reason}"


def send_event(event: dict, image_bytes: bytes, config: dict) -> dict:
    """Intenta mandar `event` + la foto a `config['api_url']`/captures.

    Nunca lanza: cualquier excepción inesperada (DNS, timeout, lo que sea) se
    atrapa y se reporta como `error` -- mandar NUNCA debe tumbar el programa
    de captura/clasificación que lo llama."""
    body_dict = dict(event)
    body_dict["image_b64"] = base64.b64encode(image_bytes).decode("ascii")
    body = json.dumps(body_dict).encode("utf-8")
    url = config["api_url"].rstrip("/") + "/captures"

    t0 = time.perf_counter()
    try:
        status, text = _signed_post(
            url,
            body,
            config["aws_profile"],
            config["aws_region"],
            config.get("send_timeout_s", 15),
        )
    except Exception as exc:  # noqa: BLE001 -- ver docstring: nunca debe propagarse
        status, text = 0, f"{type(exc).__name__}: {exc}"
    send_ms = round((time.perf_counter() - t0) * 1000, 1)

    if status in _OK_STATUSES:
        return {"send_status": "enviado", "send_error": None, "send_ms": send_ms}
    return {
        "send_status": "error",
        "send_error": f"{status} {text}"[:500],
        "send_ms": send_ms,
    }
