"""Recorte fijo -> 128x128 RGB -> normalización ImageNet (mismo contrato que
el modelo de origen del Proyecto 3, ver docs/p4/contrato-evento.md)."""

from __future__ import annotations

import numpy as np
from PIL import Image

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def crop_fixed(frame: np.ndarray, crop: dict) -> np.ndarray:
    """`crop` con w/h <= 0 significa "usar el frame completo", para que el
    stub (una imagen ya del tamaño que sea) y una cámara real con su propia
    resolución compartan el mismo config."""
    x, y, w, h = crop.get("x", 0), crop.get("y", 0), crop.get("w", 0), crop.get("h", 0)
    if w <= 0 or h <= 0:
        return frame
    return frame[y : y + h, x : x + w]


def to_model_input(frame: np.ndarray, crop: dict, image_size: int = 128) -> np.ndarray:
    cropped = crop_fixed(frame, crop)
    resized = np.array(Image.fromarray(cropped).resize((image_size, image_size), Image.BILINEAR))
    normalized = (resized.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    chw = normalized.transpose(2, 0, 1)
    return chw[np.newaxis, ...].astype(np.float32)
