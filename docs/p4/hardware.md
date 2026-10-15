# P4-03 — Preparar Raspberry Pi Zero 2 W y cámara Logitech

**Issue:** [#3](https://github.com/sanchezesteban/MLOPS_p4/issues/3) · **Responsable:** Juan Pablo (@jpdelmuro)
**Ámbito:** rúbrica 2.1, 6.1.

## Estado: completo

La Zero 2W solo trae micro-USB OTG; hizo falta un adaptador OTG micro-USB → USB-A para conectar la
Logitech (como ya anticipaba el ticket). Con el adaptador, la cámara quedó detectada y probada.

## Ficha de hardware

| Campo | Valor |
|---|---|
| Modelo | Raspberry Pi Zero 2 W Rev 1.0 |
| CPU | 4 núcleos (ARM Cortex-A53, aarch64) |
| RAM | 415 MiB visibles (512 MB físicos, resto reservado a firmware/GPU) |
| SO | Raspberry Pi OS Lite 64-bit -- Debian GNU/Linux 13 (trixie), build `pi-gen` stage2 (sin entorno de escritorio) |
| Kernel | `6.18.50+rpt-rpi-v8` (aarch64) |
| Almacenamiento | microSD 32 GB (29 G utilizables), 2.7 G usados / 25 G libres |
| Red | Wi-Fi + SSH (usuario `proyecto`), acceso remoto confirmado y usado para este ticket |
| Cámara | Logitech HD Pro Webcam C920 (USB, `idVendor=046d idProduct=082d`), vía adaptador OTG micro-USB → USB-A. Detectada por `uvcvideo`, expone `/dev/video0` (+ `/dev/video1` de metadata, típico de la C920). Captura confirmada: frame real de 640×480 |

## Software instalado

Entorno aislado en `~/edge-venv` (no se mezcla con el Python del sistema, que no trae `pip`):

```bash
python3 -m venv ~/edge-venv
~/edge-venv/bin/python -m pip install onnxruntime opencv-python-headless numpy pillow
```

| Paquete | Versión |
|---|---|
| Python | 3.13.5 |
| onnxruntime | 1.31.0 (`CPUExecutionProvider` disponible) |
| opencv-python-headless | 5.0.0 |
| pillow | 12.3.0 |
| numpy | 2.5.4 |

Todos instalados desde wheels prebuilt para `aarch64` (vía piwheels.org + pypi.org) -- nada se
compiló en la Pi.

## Swap

Ya estaba configurado de fábrica y activo, no hizo falta tocarlo:

```
Swap:  414Mi total, 0-20Mi usado según carga, 394+Mi libre
```

## Prueba de extremo a extremo (sin cámara, con stub)

Para confirmar que el runtime de inferencia funciona en el hardware real (no solo que los paquetes
importan), se corrió el pipeline completo de P4-09 con una imagen fija como entrada:

```
$ ~/edge-venv/bin/python main.py --config config.json --once
Modelo cargado: models/model_fp32_placeholder.onnx (sha256 e17e17f463a9...)
Fuente de frame: stub
[bb9e5f4a] dog (confianza 0.52, 164.6 ms)
```

~165 ms por inferencia (ResNet18 FP32, placeholder sin cuantizar) en la Zero 2 W -- da una cota
superior razonable antes de medir la variante INT8 real en P4-11.

## Foto de prueba con la cámara real

Con la Logitech ya conectada, `cv2.VideoCapture(0)` abre, lee un frame real (640×480) y lo guarda:

```
>>> cap = cv2.VideoCapture(0)
>>> cap.isOpened()
True
>>> ok, frame = cap.read()
>>> ok, frame.shape
(True, (480, 640, 3))
```

Fotos de prueba reales (con el pipeline completo de P4-09/P4-10, no solo `cv2.imwrite`):
[`evidencia/camara-gato.jpg`](evidencia/camara-gato.jpg) y
[`evidencia/camara-perro.jpg`](evidencia/camara-perro.jpg) -- detalle y predicciones en
[`docs/p4/validacion-pi.md`](validacion-pi.md).

## Criterios de «hecho»

- [x] Raspberry Pi OS Lite 64-bit en la microSD de 32 GB; SSH y Wi-Fi funcionando
- [x] Cámara Logitech recibida y detectada (`/dev/video0`, vía adaptador OTG)
- [x] Python 3 + `onnxruntime` + OpenCV (y Pillow) instalados; versiones anotadas arriba
- [x] Foto de prueba tomada desde la Pi (ver arriba)
- [x] Swap configurado (ya lo traía de fábrica, confirmado activo)
- [x] Ficha de hardware (este documento)
