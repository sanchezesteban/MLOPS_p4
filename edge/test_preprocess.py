"""Verifica la matemática de preprocess.py con valores de píxel conocidos --
no depende de cámara ni de un modelo real. Uso: `python test_preprocess.py`."""

import numpy as np

from preprocess import IMAGENET_MEAN, IMAGENET_STD, crop_fixed, to_model_input


def test_crop_fixed_recorta_la_region_pedida():
    frame = np.arange(10 * 10 * 3, dtype=np.uint8).reshape(10, 10, 3)
    cropped = crop_fixed(frame, {"x": 2, "y": 3, "w": 4, "h": 5})
    assert cropped.shape == (5, 4, 3)
    assert np.array_equal(cropped, frame[3:8, 2:6])


def test_crop_fixed_sin_wh_devuelve_el_frame_completo():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    cropped = crop_fixed(frame, {"x": 0, "y": 0, "w": 0, "h": 0})
    assert cropped is frame


def test_to_model_input_forma_y_normalizacion():
    # Imagen plana de un solo color conocido: el resize no debe mezclar valores.
    frame = np.full((64, 64, 3), (255, 0, 0), dtype=np.uint8)  # rojo puro
    model_input = to_model_input(frame, {"x": 0, "y": 0, "w": 0, "h": 0}, image_size=128)

    assert model_input.shape == (1, 3, 128, 128)
    assert model_input.dtype == np.float32

    expected_r = (1.0 - IMAGENET_MEAN[0]) / IMAGENET_STD[0]
    expected_g = (0.0 - IMAGENET_MEAN[1]) / IMAGENET_STD[1]
    expected_b = (0.0 - IMAGENET_MEAN[2]) / IMAGENET_STD[2]

    assert np.allclose(model_input[0, 0], expected_r, atol=1e-4)
    assert np.allclose(model_input[0, 1], expected_g, atol=1e-4)
    assert np.allclose(model_input[0, 2], expected_b, atol=1e-4)


if __name__ == "__main__":
    test_crop_fixed_recorta_la_region_pedida()
    test_crop_fixed_sin_wh_devuelve_el_frame_completo()
    test_to_model_input_forma_y_normalizacion()
    print("OK: las 3 pruebas de preprocess.py pasaron")
