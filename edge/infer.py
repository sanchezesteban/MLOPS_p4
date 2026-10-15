"""Carga el ONNX activo y corre inferencia local con onnxruntime."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Model:
    def __init__(self, model_path: str | Path):
        self.path = Path(model_path)
        self.sha256 = sha256_file(self.path)
        self._session = ort.InferenceSession(str(self.path), providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    def predict(self, model_input: np.ndarray) -> tuple[int, float, float]:
        """Devuelve (clase predicha, confianza, latencia_ms). La latencia
        mide solo esta llamada (la corrida del modelo); `main.py` le suma el
        tiempo de preprocesamiento para armar el `latency_ms` del contrato
        del evento (preprocesamiento + inferencia, sin envío)."""
        t0 = time.perf_counter()
        (logits,) = self._session.run(None, {self._input_name: model_input})
        latency_ms = (time.perf_counter() - t0) * 1000

        shifted = logits[0] - logits[0].max()
        exp = np.exp(shifted)
        probs = exp / exp.sum()
        predicted = int(probs.argmax())
        confidence = float(probs[predicted])
        return predicted, confidence, latency_ms
