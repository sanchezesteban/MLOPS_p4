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

## Comparación: laptop (FP32 e INT8) vs. Pi (INT8)

10 recortes de **validación** (`data/derived/manifests/v0.1.1`, split `val`, el mismo dataset de
P4-02/P4-06 -- no se usó ninguna imagen de calibración ni de test), 5 gatos y 5 perros, corridos con
el mismo `edge/preprocess.py` (recorte completo -- ya son crops, no frames crudos -- 128×128,
normalización ImageNet) en los tres: laptop FP32, laptop INT8 (mismo `.onnx` que la Pi, para aislar
el efecto de cuantizar del efecto de dispositivo) y Pi INT8.

| Archivo | Real | Laptop FP32 | Laptop INT8 | Pi INT8 | ms (Pi) | Coincide |
|---|---|---|---|---|---|---|
| `000005_000004.jpg` | cat | cat 0.9998 | cat 0.9998 | cat 0.9998 | 103.5 | sí |
| `000010_000008.jpg` | cat | cat 0.9946 | cat 0.9947 | cat 0.9947 | 63.5 | sí |
| `000039_000064.jpg` | dog | dog 0.9995 | dog 0.9995 | dog 0.9995 | 63.3 | sí |
| `000043_000069.jpg` | dog | dog 0.9993 | dog 0.9994 | dog 0.9994 | 63.9 | sí |
| `000625_000624.jpg` | cat | cat 0.7034 | cat 0.6185 | cat 0.6185 | 64.8 | sí |
| `000630_000630.jpg` | cat | cat 0.9957 | cat 0.9960 | cat 0.9960 | 68.7 | sí |
| `000633_000627.jpg` | cat | **dog** 0.6443 | **dog** 0.6660 | **dog** 0.6660 | 65.0 | sí (mismo error) |
| `000657_000661.jpg` | dog | dog 0.9998 | dog 0.9999 | dog 0.9999 | 63.2 | sí |
| `000658_000662.jpg` | dog | dog 0.9989 | dog 0.9990 | dog 0.9990 | 63.2 | sí |
| `000663_000667.jpg` | dog | dog 0.8981 | dog 0.9323 | dog 0.9323 | 63.5 | sí |

**Laptop INT8 y Pi INT8 dan exactamente las mismas confianzas en las 10 imágenes** (no solo la misma
clase) -- confirma que la Pi corre el modelo correctamente, sin ninguna diferencia introducida por el
dispositivo; toda la diferencia frente al FP32 es pura cuantización, no un problema de la Zero 2W.
**10/10 coinciden también entre FP32 y INT8** (incluido el mismo error en `000633_000627.jpg`,
consistente con la comparación formal de calidad de P4-06). Latencia en la Pi: ~63-104 ms típico
(INT8, ya sin incluir lectura de cámara -- ver corrección de P4-09) -- cifra preliminar, el benchmark
formal con calentamiento y ≥100 corridas es P4-11.

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
entrada. Nota: las latencias de esta sección se midieron antes de la corrección de P4-09 que excluye
la lectura de la cámara de `latency_ms` (por eso salen ~360-390 ms aquí); con la corrección, la
latencia real de preprocesamiento + inferencia con cámara queda en ~90-215 ms (ver la sección "Sin
red sigue clasificando" abajo, medida después del fix).

## Sin red sigue clasificando

`edge/main.py`, `infer.py`, `preprocess.py` y `frame_source.py` no importan `socket`, `requests` ni
ningún cliente HTTP -- el envío a AWS (P4-12) es un paso aparte y posterior que todavía no existe en
este código. Pero "por construcción" no basta como evidencia (el evaluador va a desconectar la red de
verdad y mirar), así que se hizo la prueba real, con el mismo procedimiento que se usará en la demo:

**Procedimiento** (reproducible, documentado para ensayarlo antes de la demo):

```bash
# 1. Arrancar el programa en modo intervalo dentro de tmux (sobrevive al corte de red)
tmux new-session -d -s edge '~/edge-venv/bin/python main.py --config config.json'

# 2. Apagar el wifi con regreso automático, como unidad systemd independiente de la
#    sesión SSH (si no, el corte de red mata también al propio comando de reconexión)
sudo systemd-run --unit=wifi-toggle-test bash -c 'nmcli radio wifi off; sleep 65; nmcli radio wifi on'
```

**Resultado real** (15 de octubre, 2026):

- `08:09:24` -- se lanza el apagado de wifi.
- El SSH (y Tailscale, que corre sobre la misma wifi) se cae casi de inmediato, como se esperaba.
- `08:10:47` -- primer reintento de SSH que conecta: la red ya volvió.
- `nmcli radio wifi` confirma `enabled` y `wlan0: connected` al reconectar.

Con `tmux attach`/`capture-pane` a la sesión `edge`, y revisando `ls -la --time-style=full-iso
capturas/*.json`: **17 capturas seguidas entre las 08:09:28 y las 08:10:54** (86 segundos, cubriendo
toda la ventana sin red y un poco antes/después), cada ~5-6s según el `capture_interval_seconds` del
config -- nunca se detuvo:

```
08:09:28  08:09:33  08:09:39  08:09:44  08:09:49  08:09:55  08:10:00  08:10:06  08:10:11
08:10:16  08:10:22  08:10:27  08:10:33  08:10:38  08:10:43  08:10:49  08:10:54
```

Latencia típica durante la prueba (ya con la corrección de P4-09, sin contar lectura de cámara):
~105-135 ms, con dos picos de 172 ms y 215 ms (probablemente por el I/O del `systemd-run`/apagado de
wifi compitiendo por CPU, no por el modelo en sí).

## Criterios de «hecho»

- [x] SHA-256 del modelo cargado = el publicado en #5/#7 (verificado en laptop y Pi), mostrado al
  arrancar y en cada evento
- [x] 10 imágenes de validación: misma clase que en la laptop, confianza similar (10/10)
- [x] Objetos reales de gato/perro cambian la predicción (ver tabla arriba)
- [x] Con la red desconectada sigue capturando y clasificando -- probado de verdad, no solo por
  construcción (ver procedimiento y resultado arriba)
