# Autoevaluación del equipo (P4-24)

Aplicación del prompt de evaluación del Proyecto 4 sobre el repositorio al 16-oct-2026.
**Estado: PROVISIONAL.** Se basa en archivos y registros recalculados; los criterios que se
observan en vivo (demostración dirigida) y el video se marcan como pendientes de observación.
Distingue: **recalculado** (verificado aritméticamente desde los archivos), **documentado**
(salida de comandos registrada por el equipo) y **pendiente** (requiere observación).

## Requisitos mínimos

| Requisito | Estado | Evidencia | Qué falta |
|---|---|---|---|
| M1 · Variante procede del modelo del P3 | CUMPLE | SHA del `best.pt` = registro del P3; accuracy de validación reproducida exacta (0.9618320610687023); `conversion_log.json` liga entrada `f759cde2…` → salida `58effa03…` | — |
| M2 · Clasificación local en edge físico con cámara | CUMPLE (documentado) · PENDIENTE de observación | `validacion-pi.md` (laptop INT8 = Pi INT8 en 10/10; corte de red real), `estabilidad-procedimiento.md` | Demostración en vivo |
| M3 · Capturas reales en AWS y en el portal previo | CUMPLE (recalculado/documentado) · PENDIENTE de observación | `evidencias/aws/eventos.csv` (56 eventos con imagen en S3), `capturas-api-real.md` | Captura dirigida en vivo |

Compuerta: **NO ACTIVADA** según la evidencia; se confirma en la demostración.

## Calificación base

| Puntos | Criterio | Evidencia | Riesgo o lo que falta |
|---|---|---|---|
| 5 / 5 | 1.1 Continuidad | `modelo-origen.md`, `verify_checkpoint.json`, `artefactos.md` | — |
| 10 / 10 | 1.2 Optimización real | `app/edge/convert.py`, `conversion_log.json`, INT8 cargado en la Pi (SHA impreso al arrancar) | — |
| 10 / 10 | 1.3 Calidad | Recalculado: 131 filas, sin duplicados; accuracy y F1 macro 0.9618 en original e INT8; caída 0.00 pp; 464 IDs de calibración solo de train, 0 cruces con val/test | — |
| 5 / 5 | 2.1 Cámara | Fotos reales de la C920; 56 capturas | Objetos elegidos por el evaluador en vivo |
| 5 / 5 | 2.2 Entrada y clases | Preprocesamiento igual al del P3 (diferencia ~1e-8); 10/10 laptop = Pi | — |
| 10 / 10 | 2.3 Inferencia local | INT8 en la Pi; 17 capturas con Wi-Fi apagado | Prueba sin red en vivo |
| 5 / 5 | 2.4 Operación estable | 5 min, 0 errores, reinicio + captura nueva | — |
| 5 / 5 | 3.1 Condiciones equivalentes | Misma Pi, corrida, entrada, runtime e hilos; original como ONNX FP32 de los mismos pesos (justificado en `reporte-optimizacion.md`) | — |
| 5 / 5 | 3.2 Mediciones auditables | Recalculado: 10 + 100 por variante; p50/p95 coinciden; envío medido aparte (`send_ms`) | — |
| 5 / 5 | 3.3 Mejora y decisión | −74.7 % tamaño; ×2.03 p50 (significativo); intercambio explicado | — |
| 5 / 5 | 4.1 Evento completo | Recalculado: los 56 eventos con ID, fecha con zona, clase, confianza 0.50–0.9999, dispositivo, versión y SHA del modelo | — |
| 5 / 5 | 4.2 Persistencia real en AWS | Export con versión de cada JPEG; usuario evaluador de solo lectura | Consulta en vivo |
| 5 / 5 | 4.3 Fallo y reintento | 503 → reintento → un solo registro (`envio-aws.md`) | Repetirlo en vivo |
| 3 / 3 | 5.1 Integración | Sección en el menú del portal P1–P3 desplegado en EC2 | — |
| 4 / 4 | 5.2 Imagen y metadatos | Cruce de `8d026b3c…` portal ↔ API ↔ export; orden; recorte | — |
| 3 / 3 | 5.3 Consulta funcional | «Actualizar», estados de carga, vacío y error | — |
| 3.5 / 4 | 6.1 Instrucciones | README completo, hardware y versiones | Nadie siguió el README desde cero en un clon limpio |
| 4 / 4 | 6.2 Comprobaciones repetibles | `verificacion-manual.md` + pruebas automatizadas (46 Python, 3 Pi, 190 portal) | — |
| 2 / 2 | 6.3 Configuración y acceso | `edge/config.example.json` sin secretos; evaluador con vencimiento | — |

| Sección | Puntos |
|---|---|
| 1. Optimización y calidad | 25 / 25 |
| 2. Clasificación en edge | 25 / 25 |
| 3. Recursos y mejora | 15 / 15 |
| 4. AWS | 15 / 15 |
| 5. Portal | 10 / 10 |
| 6. Reproducción | 9.5 / 10 |
| **Base** | **99.5 / 100** |

## Comparación antes y después

| Dato | Original del P3 | Optimizado | Cálculo | ¿Coincide con lo reportado? |
|---|---|---|---|---|
| Versión y SHA-256 | `1.0.0` · `f759cde2…ab7d9` | `resnet18-p3-v1.0.0-int8` · `58effa03…a1bb` | — | Sí |
| Tamaño | 45 224 191 B (ONNX FP32) | 11 430 716 B | −74.72 % | Sí |
| Accuracy val | 0.961832 | 0.961832 | 0.00 pp | Sí |
| F1 macro val | 0.961823 | 0.961823 | 0.00 | Sí |
| Latencia p50 / p95 en la Pi | 142.24 / 148.13 ms | 70.18 / 71.62 ms | ×2.03 / ×2.07 | Sí (recalculado) |
| Válidas / calentamiento | 100 / 10 | 100 / 10 | — | Sí |

## Video extra

| Puntos | Criterio | Estado |
|---|---|---|
| PENDIENTE / 5 | V1 | Video en preparación |
| PENDIENTE / 5 | V2 | Video en preparación |
| PENDIENTE / 5 | V3 | Video en preparación |

## Resultado provisional

```text
Base confirmada por archivos:  99.5 / 100 (sujeta a la demostración en vivo)
Video extra:                   pendiente (hasta 15)
Compuerta:                     no activada según la evidencia
```

## Límites de esta autoevaluación

- No se observó la demostración en vivo; M2, M3, 2.1, 2.3, 4.2 y 4.3 se confirman en ella.
- No se siguió el README desde cero en un clon limpio (6.1).
- Las capturas tomadas durante el video o la demostración se agregan a AWS después del export de
  56 eventos; el export se repite al final.
