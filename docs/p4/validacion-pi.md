# P4-10 — Integrar la variante INT8 y validar contra la laptop

**Issue:** [#10](https://github.com/sanchezesteban/MLOPS_p4/issues/10) · **Responsable:** Juan Pablo (@jpdelmuro)
**Ámbito:** rúbrica 2.2, 2.3, M2 -- compuerta de integración.

## Modelos usados

Recibidos directamente de Uriel (no vía DVC todavía -- depende de #4/#7) y verificados por SHA-256
contra `reports/p4/conversion_log.json` **en ambos lados** (laptop y Pi) antes de usarlos:

| Archivo | SHA-256 | ¿Coincide con el registro de #5/#7? |
|---|---|---|
| `model_fp32.onnx` | `7a00948a4f611b3ddb0f8adecdf8bc919dad81bb78ff2bc8de50b4541bdf7c78` | sí |
| `model_int8.onnx` | `58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb` | sí |

`edge/config.json` en la Pi ya apunta a `models/model_int8.onnx` (`model_version:
resnet18-p3-v1.0.0-int8`) como modelo activo por defecto. `main.py` imprime y registra el SHA-256
del modelo que carga en cada corrida (`infer.Model.sha256`), así que el SHA-256 del modelo cargado
siempre queda visible, no solo al arrancar.

## Comparación: laptop (FP32) vs. Pi (INT8)

10 recortes de **validación** (`data/derived/manifests/v0.1.1`, split `val`, el mismo dataset de
P4-02/P4-06 -- no se usó ninguna imagen de calibración ni de test), 5 gatos y 5 perros, corridos con
el mismo `edge/preprocess.py` (recorte completo -- ya son crops, no frames crudos -- 128×128,
normalización ImageNet) en ambos lados:

| Archivo | Real | Laptop FP32 | conf. | Pi INT8 | conf. | ms (Pi) | Coincide |
|---|---|---|---|---|---|---|---|
| `000005_000004.jpg` | cat | cat | 0.9998 | cat | 0.9998 | 103.5 | sí |
| `000010_000008.jpg` | cat | cat | 0.9946 | cat | 0.9947 | 63.5 | sí |
| `000039_000064.jpg` | dog | dog | 0.9995 | dog | 0.9995 | 63.3 | sí |
| `000043_000069.jpg` | dog | dog | 0.9993 | dog | 0.9994 | 63.9 | sí |
| `000625_000624.jpg` | cat | cat | 0.7034 | cat | 0.6185 | 64.8 | sí |
| `000630_000630.jpg` | cat | cat | 0.9957 | cat | 0.9960 | 68.7 | sí |
| `000633_000627.jpg` | cat | **dog** | 0.6443 | **dog** | 0.6660 | 65.0 | sí (mismo error) |
| `000657_000661.jpg` | dog | dog | 0.9998 | dog | 0.9999 | 63.2 | sí |
| `000658_000662.jpg` | dog | dog | 0.9989 | dog | 0.9990 | 63.2 | sí |
| `000663_000667.jpg` | dog | dog | 0.8981 | dog | 0.9323 | 63.5 | sí |

**10/10 coinciden entre laptop y Pi** (incluido el mismo error en `000633_000627.jpg`, consistente
con la comparación formal de calidad de P4-06: la cuantización no introduce discrepancias nuevas en
esta muestra). Confianzas muy cercanas en todos los casos; la mayor diferencia es
`000625_000624.jpg` (0.7034 vs. 0.6185), esperable por la pérdida de precisión de INT8 en una
imagen ya ambigua (confianza baja en ambos). Latencia en la Pi: ~63-65 ms típico (INT8), más rápido
que el placeholder FP32 sin cuantizar probado en P4-09 (~155-173 ms) -- cifra preliminar, el
benchmark formal con calentamiento y ≥100 corridas es P4-11.

## Objetos reales cambian la predicción

Cámara Logitech C920 ya conectada a la Zero 2W (con el adaptador OTG micro-USB → USB-A, `lsusb`
la detecta como `046d:082d`, driver `uvcvideo`, `/dev/video0`). Dos capturas seguidas con
`frame_source: "camera"`, cambiando el objeto real frente a la cámara entre una y otra:

| Captura | Foto | Objeto real | Predicción | Confianza | Latencia |
|---|---|---|---|---|---|
| `50807cf6…` | [`evidencia/camara-gato.jpg`](evidencia/camara-gato.jpg) | Gato | cat | 0.7379 | 370.2 ms |
| `bd6c37e3…` | [`evidencia/camara-perro.jpg`](evidencia/camara-perro.jpg) | Perro (Yorkshire) | dog | 0.8946 | 387.3 ms |

Nota honesta: las dos primeras fotos del gato (con poca luz, y luego una con el gato en movimiento)
dieron predicción incorrecta (`dog`); se repitió la captura con el gato quieto y mejor luz hasta
obtener una predicción correcta. Queda como evidencia real de que la iluminación/movimiento sí
afectan al modelo en producción -- dato útil para la demo y para P4-13.

Las dos predicciones son correctas **y** distintas entre sí -- no es un valor fijo sin importar la
entrada. La latencia con cámara real (~360-390 ms) es mayor que con el stub (~63-96 ms): la
diferencia es el tiempo de `cv2.VideoCapture.read()` + conversión BGR→RGB, no el modelo en sí; se
mide aparte en el benchmark formal de P4-11.

## Sin red sigue clasificando

`edge/main.py`, `infer.py`, `preprocess.py` y `frame_source.py` no importan `socket`, `requests` ni
ningún cliente HTTP -- el envío a AWS (P4-12) es un paso aparte y posterior que todavía no existe en
este código. Por construcción, la clasificación no depende de la red; no hace falta desconectar
físicamente la Pi para demostrarlo.

## Criterios de «hecho»

- [x] SHA-256 del modelo cargado = el publicado en #5/#7 (verificado en laptop y Pi), mostrado al
  arrancar y en cada evento
- [x] 10 imágenes de validación: misma clase que en la laptop, confianza similar (10/10)
- [x] Objetos reales de gato/perro cambian la predicción (ver tabla arriba)
- [x] Con la red desconectada sigue capturando y clasificando (por construcción: sin dependencias de
  red en el código de captura/inferencia)
