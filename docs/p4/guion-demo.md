# Guion de la demostración y del video (P4-22, P4-23)

## Antes de empezar (15 min antes)

| Quién | Qué |
|---|---|
| Ikram | `bash scripts/p4_portal.sh start` y `status` (si estaba apagado); `bash scripts/p4_ingesta_fallo.sh status` → **habilitada** |
| Juan Pablo | Pi encendida con cámara, adaptador OTG y fuente; SSH abierto; `config.json` con `frame_source: camera`; buena luz |
| Juan Pablo | Fotos de gatos y perros que **no** sean del dataset (impresas o en pantalla), llenando el cuadro |
| Uriel | Portal abierto en http://3.133.248.228 → «Capturas Edge» |
| Esteban | Ficha de entrega y este guion abiertos; cronómetro |

## Demostración dirigida (10–15 min)

Sigue el orden de la evaluación (Fase 4B). El evaluador puede elegir objetos e IDs.

| Min | Paso | Quién | Qué se muestra | Criterio |
|---|---|---|---|---|
| 0–1 | Identificar modelo y dispositivo | Esteban | Ficha: SHA del `best.pt` (`f759cde2…`) y del INT8 (`58effa03…`), Pi Zero 2 W, onnxruntime 1.31.0 | M1, 1.1 |
| 1–2 | Arrancar el programa | Juan Pablo | `main.py --config config.json` imprime el SHA del modelo cargado y «Fuente de frame: camera» | 2.3 |
| 2–4 | Capturas nuevas | Juan Pablo | El evaluador elige gatos y perros; la predicción cambia según el objeto; clase, confianza y ms en consola | 2.1, 2.2 |
| 4–5 | Llegada al portal | Uriel | «Actualizar»: la captura aparece arriba con el mismo `capture_id`, clase y confianza | M3, 5.2, 5.3 |
| 5–7 | Sin red | Juan Pablo | `bash sin_red_demo.sh 65`: al reconectar, `tmux capture-pane -t edge -p` muestra que siguió clasificando durante el corte | M2, 2.3 |
| 7–8 | Captura nueva tras reconectar | Juan Pablo | `--once` → `enviado`; `bash verificar_captura.sh <id>` → OK | 4.2 |
| 8–9 | Persistencia en AWS | Ikram | `evidence.py get <id>`: ítem en DynamoDB y versión del JPEG en S3 (o la consola con el usuario evaluador) | 4.1, 4.2 |
| 9–11 | Fallo y reintento | Ikram y Juan Pablo | `p4_ingesta_fallo.sh off` → captura → **ERROR 503** visible → `on` → `--retry-failed` → `enviado` → `get` muestra **un solo** registro | 4.3 |
| 11–12 | Reinicio | Juan Pablo | Ctrl+C, arrancar de nuevo y una captura nueva que llega al portal | 2.4 |
| 12–14 | Evidencia recalculable | Esteban | `quality_predictions.csv`, `benchmark.csv`, `eventos.csv`; el evaluador elige una fila | 1.3, 3.2, 6.2 |

**Si algo falla:** se dice en voz alta y se muestra el error; los fallos reales visibles cuentan
a favor (2.4). Plan B de cada paso: la evidencia ya documentada en
[`verificacion-manual.md`](verificacion-manual.md).

**Al terminar:** Ikram deja la ingesta en `on` y corre el export
(`evidence.py export --out ../evidencias/aws`) para que el repo incluya las capturas de la demo.

## Video (3–5 min, +15 puntos)

Grabar pantalla dividida o alternar: cámara física apuntando a la Pi + consola SSH + portal.
Una toma continua sin cortes en los pasos 2–4 hace evidente que no hay edición.

| Tiempo | Toma | Debe verse | Puntos |
|---|---|---|---|
| 0:00–0:20 | Presentación | Pi Zero 2 W con la cámara; «modelo INT8 del Proyecto 3» | — |
| 0:20–1:30 | Clasificación en vivo | Un gato y un perro frente a la cámara; la consola muestra `cat` y luego `dog`, con confianza y ms | **V1** |
| 1:30–2:30 | Llegada a AWS y portal | La consola dice `enviado`; en el portal, «Actualizar» y aparecen las capturas nuevas | **V2** |
| 2:30–3:30 | Seguir una misma captura | Leer en voz alta el `capture_id`, la hora y la clase en la consola; hacer zoom a la misma tarjeta del portal (mismo ID completo, hora, clase y foto); opcional: el mismo ID en DynamoDB | **V3** |
| 3:30–4:30 | Cierre opcional | Prueba sin red (contador de capturas siguiendo) o fallo 503 y reintento | — |

Checklist del video: enlace accesible sin iniciar sesión (probarlo en otra cuenta), duración
3–5 min, el ID completo legible en la consola y en el portal.
