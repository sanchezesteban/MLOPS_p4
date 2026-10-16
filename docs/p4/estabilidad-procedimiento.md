# P4-13 — Estabilidad: 5 minutos, reinicio y 20 capturas

**Issue:** [#13](https://github.com/sanchezesteban/MLOPS_p4/issues/13) · **Responsable:** Juan Pablo (@jpdelmuro)
**Ámbito:** rúbrica 2.4.

## Estado: completo

Ejecutado en la Pi física (Zero 2W + cámara Logitech C920), no en la laptop ni con un video
simulado -- el criterio depende de la cámara real funcionando sin caerse.

## Un bug real encontrado y corregido en el camino

El primer intento (5 minutos pedidos) se cortó solo a los ~1 min 47 s, sin ningún error visible.
Investigando: `main.py` solo atrapaba `KeyboardInterrupt` en el loop continuo -- cualquier otra
excepción (sospecha más probable: un glitch transitorio de la cámara USB) tumbaba **todo el
programa**, no solo esa captura, sin dejar rastro. Es exactamente el tipo de falla que esta prueba
está diseñada para encontrar.

Corrección en `edge/main.py`: cada vuelta del loop ahora atrapa cualquier excepción, la registra en
`capturas/errors.log` con traceback completo, y sigue con la siguiente captura en vez de morir. Ver
el commit `ecac8d2` en la rama `p4-12-envio-aws` (de ahí parte esta rama).

También se descubrió por el camino que la primera ronda de fotos (mostrando el dataset del teléfono
a la cámara) clasificaba mal sistemáticamente: las fotos del teléfono quedaban con barras negras
(bisel + fondo) dentro del cuadro, diluyendo al animal en el resize a 128×128. Corregido ajustando
el encuadre físico del teléfono (llenando el cuadro, sin barras) -- verificado con 10 fotos de
prueba sin enviar (9/10 correctas, confianzas 0.52-1.00) antes de la corrida oficial.

## Resultado de la corrida real (segundo intento, con el fix)

- **Inicio:** 2026-10-16 12:44:47 (CST). **Detenida manualmente con Ctrl+C** tras cumplirse los 5
  minutos -- `main.py` imprimió "Detenido por el usuario." (cierre limpio por `KeyboardInterrupt`,
  no un crash).
- **55 capturas** durante la sesión continua (muy por arriba de las 20 mínimas): **30 gato, 25
  perro**.
- **`capturas/errors.log`: no se generó** -- cero errores de captura en toda la corrida.
- **Envío:** las 55 quedaron en `send_status: enviado` (0 en `error`). Log completo:
  [`evidencia/estabilidad/sesion.log`](evidencia/estabilidad/sesion.log) (salida de consola) y
  [`evidencia/estabilidad/log-estabilidad.jsonl`](evidencia/estabilidad/log-estabilidad.jsonl)
  (bitácora `pendiente`/`enviado` de cada intento).
- **Lista completa de los 56 `capture_id`** (55 de la sesión + 1 del reinicio, en orden):
  [`evidencia/estabilidad/capture_ids.txt`](evidencia/estabilidad/capture_ids.txt).

### Reinicio + captura nueva que llega al portal

```
$ ~/edge-venv/bin/python main.py --config config.json --once
[8d026b3c] cat (confianza 0.88, 136.0 ms) -- enviado (648.4 ms)
```

Confirmado contra la API de lectura pública (la misma que usa el portal, sin credenciales):
`8d026b3c-08ed-4770-9632-0ecd2d38b843` aparece en `GET /captures?limit=50`.

## Criterios de «hecho»

- [x] 5 minutos de operación continua sin caídas (con el fix -- el primer intento sin el fix
  reveló el bug de arriba, que ya quedó corregido)
- [x] Reiniciar el programa y hacer una captura nueva que llega al portal
- [x] 20 capturas repartidas entre gato y perro enviadas a AWS (55: 30 gato, 25 perro)
- [x] Errores reales quedan registrados (no hubo ninguno en la corrida final; el mecanismo de
  registro -- `errors.log` -- sí quedó verificado y corregido a partir de la falla del primer intento)

## Scripts de apoyo

- [`edge/sin_red_demo.sh`](../../edge/sin_red_demo.sh) -- mismo patrón para la demo (P4-22/P4-23):
  "desconectar red → sigue clasificando → reconectar → llega al portal".
- [`edge/verificar_captura.sh`](../../edge/verificar_captura.sh) -- confirma por la API pública que
  una captura llegó, igual que lo vería el portal.
