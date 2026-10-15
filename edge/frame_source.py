"""Fuente de frame intercambiable: cámara real o una imagen fija.

Mientras no llega la cámara Logitech (P4-03), `StubFrameSource` permite
desarrollar y probar el resto del pipeline (P4-09) con una imagen fija. El
día que la cámara esté conectada, basta cambiar `frame_source` a `camera`
en el config -- el resto del programa no cambia.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


class FrameSource:
    def read(self) -> np.ndarray:
        raise NotImplementedError

    def close(self) -> None:
        pass


class StubFrameSource(FrameSource):
    """Devuelve siempre la misma imagen fija."""

    def __init__(self, image_path: str | Path):
        self._frame = np.array(Image.open(image_path).convert("RGB"))

    def read(self) -> np.ndarray:
        return self._frame.copy()


class CameraFrameSource(FrameSource):
    """Cámara real vía V4L2 (OpenCV). Requiere `/dev/video0` detectado (P4-03)."""

    def __init__(self, device_index: int = 0):
        import cv2

        self._cap = cv2.VideoCapture(device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la cámara en el índice {device_index}")

    def read(self) -> np.ndarray:
        import cv2

        ok, frame_bgr = self._cap.read()
        if not ok:
            raise RuntimeError("No se pudo leer un frame de la cámara")
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        self._cap.release()


def build_frame_source(config: dict) -> FrameSource:
    kind = config.get("frame_source", "stub")
    if kind == "stub":
        return StubFrameSource(config["stub_image_path"])
    if kind == "camera":
        return CameraFrameSource(config.get("camera_index", 0))
    raise ValueError(f"frame_source desconocido: {kind!r} (usa 'stub' o 'camera')")
