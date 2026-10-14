# Contrato del evento de captura — v1

Acuerdo entre los tres frentes del Proyecto 4 (issue #1). Es el **único punto de
acoplamiento** entre la Raspberry Pi, AWS y el portal: mientras todos respeten este
documento, cada frente puede desarrollar y probar por separado (la Pi contra el
simulador, AWS con eventos de prueba y el portal con un JSON de ejemplo).

| Frente | Responsable | Usa el contrato para |
|---|---|---|
| Dispositivo (Pi) | Juan Pablo | Generar y enviar cada evento (#9, #12) |
| AWS | Ikram | Recibir, validar, persistir y exponer eventos (#16, #17) |
| Portal | Uriel | Mostrar los eventos en «Capturas Edge» (#14, #15) |

Cambiar este contrato requiere un PR aprobado por los tres responsables. Cada cambio
incrementa la versión (`v1` → `v2`) y se anota en el historial al final.

## Recorrido

```text
 Raspberry Pi                          AWS                               Portal
 ───────────                           ───                               ──────
 captura → recorte → inferencia
 genera capture_id + metadatos
 guarda JPEG + JSON en microSD
        │  POST /captures  (evento)
        └──────────────────────────► valida campos
                                     ¿capture_id ya existe? → no duplica
                                     guarda imagen (S3) + metadatos
                                     agrega received_at, image_key
                                              │  GET /captures
                                              └──────────────────────► lista reciente → antigua
                                                                       imagen + metadatos
```

## Campos del evento

| Campo | Tipo | Obligatorio | Lo genera | Regla |
|---|---|---|---|---|
| `capture_id` | string (UUID v4) | Sí | Pi | Se genera **una sola vez** por captura y se reutiliza en todos los reintentos. |
| `captured_at` | string ISO-8601 | Sí | Pi | Con zona horaria. Ej.: `2026-10-13T10:15:02-06:00`. |
| `device_id` | string | Sí | Pi | Identidad fija del dispositivo. Valor acordado: `rpi-zero2w-01`. |
| `model_version` | string | Sí | Pi | Versión del artefacto cargado. Ej.: `resnet18-p3-v1.0.0-int8`. |
| `model_sha256` | string (64 hex) | Sí | Pi | SHA-256 del archivo `.onnx` cargado; debe coincidir con el publicado (#7). |
| `predicted_class` | string | Sí | Pi | Solo `cat` o `dog`. |
| `confidence` | número | Sí | Pi | Entre `0` y `1`: probabilidad **softmax** de la clase predicha (argmax). El ONNX devuelve *logits*; la Pi aplica softmax. |
| `latency_ms` | número | Sí | Pi | Preprocesamiento + inferencia. **No** incluye el envío. |
| `crop` | objeto `{x, y, w, h}` | Sí | Pi | Región clasificada en píxeles de la imagen original. Si no hay recorte: `null`. |
| `image` | archivo JPEG | Sí | Pi | La fotografía capturada, tal cual se clasificó (ver «Envío»). |
| `received_at` | string ISO-8601 | — | AWS | Momento de recepción en AWS (UTC). La Pi no lo envía. |
| `image_key` | string | — | AWS | Clave del objeto en S3. Ej.: `captures/2026/10/13/<capture_id>.jpg`. |

### Modelo y clases (fijos del Proyecto 3)

| Dato | Valor |
|---|---|
| Clases | `{0: "cat", 1: "dog"}` — mismo orden que `app/class_map.json` |
| Entrada | 128 × 128, RGB (no BGR) |
| Normalización | media `[0.485, 0.456, 0.406]`, desviación `[0.229, 0.224, 0.225]` |

## Envío: Pi → AWS

**`POST /captures`** con cuerpo JSON. La imagen viaja en el campo `image_b64`
(JPEG codificado en base64, máximo 1 MB antes de codificar).

```json
{
  "capture_id": "3f2b8c1e-6d4a-4b9e-9a51-0c7e2f1d8a22",
  "captured_at": "2026-10-13T10:15:02-06:00",
  "device_id": "rpi-zero2w-01",
  "model_version": "resnet18-p3-v1.0.0-int8",
  "model_sha256": "<64 caracteres hex>",
  "predicted_class": "dog",
  "confidence": 0.93,
  "latency_ms": 412.7,
  "crop": { "x": 80, "y": 40, "w": 480, "h": 400 },
  "image_b64": "<JPEG en base64>"
}
```

### Respuestas

| Código | Significado | Qué hace la Pi |
|---|---|---|
| `201 Created` | Evento nuevo guardado | Marca la captura como **enviada** |
| `200 OK` | Ese `capture_id` ya existía; **no se duplicó** ni se sobrescribió | Marca la captura como **enviada** |
| `400 Bad Request` | Campo faltante o inválido (el cuerpo dice cuál) | Marca **error** y muestra el mensaje; reintentar no sirve hasta corregir |
| `5xx` o sin red | Falla de AWS o de conexión | Marca **error** y permite **reintento manual** con el mismo `capture_id` |

Respuesta de `201`/`200`:

```json
{ "capture_id": "3f2b8c1e-…", "received_at": "2026-10-13T16:15:03Z", "image_key": "captures/2026/10/13/3f2b8c1e-….jpg", "duplicate": false }
```

### Regla anti-duplicados

AWS guarda el evento con **escritura condicional por `capture_id`**: si el ID ya existe,
no escribe de nuevo y responde `200` con `"duplicate": true`. Así, un reintento después
de un fallo nunca crea dos registros. Se demuestra en la prueba de fallo y reintento
(criterio 4.3 de la rúbrica).

## Registro local en la Pi

Cada captura se guarda en la microSD **antes** de enviarse, para que la clasificación
no dependa de la red:

```text
captures/
├── <capture_id>.jpg
└── log.jsonl        ← una línea por captura: todos los campos + send_status
```

`send_status` toma uno de tres valores: `pendiente`, `enviado` o `error` (con
`send_error` y `send_ms`, el tiempo de envío medido aparte de la inferencia).

## Lectura: AWS → portal

**`GET /captures?limit=50`** devuelve las capturas de la más reciente a la más antigua
(por `captured_at` normalizado a UTC). Si dos capturas tienen el mismo `captured_at`, el
portal desempata por `received_at` (más reciente primero). Cada elemento trae todos los campos del evento, excepto `image_b64`,
más `image_url`: una URL firmada de S3 válida por 15 minutos. Expira: el portal la renueva
volviendo a pedir `GET /captures` (botón «Actualizar» o refresco automático); no debe
guardarla.

```json
{
  "items": [
    {
      "capture_id": "3f2b8c1e-…",
      "captured_at": "2026-10-13T10:15:02-06:00",
      "received_at": "2026-10-13T16:15:03Z",
      "device_id": "rpi-zero2w-01",
      "model_version": "resnet18-p3-v1.0.0-int8",
      "model_sha256": "<64 caracteres hex>",
      "predicted_class": "dog",
      "confidence": 0.93,
      "latency_ms": 412.7,
      "crop": { "x": 80, "y": 40, "w": 480, "h": 400 },
      "image_key": "captures/2026/10/13/3f2b8c1e-….jpg",
      "image_url": "https://…firmada…"
    }
  ]
}
```

El portal muestra como mínimo: foto, clase, confianza, `captured_at`, `capture_id`,
`device_id` y `model_version`, con mensajes para carga, lista vacía y error.

## Seguridad

- La credencial de la Pi solo permite `POST /captures`; no lee ni borra.
- Ninguna credencial, URL privada o token va en Git: se configuran en archivos
  ignorados (`.env`, `edge/config.local.*`) a partir de plantillas `*.example`.

## Historial

| Versión | Fecha | Cambio |
|---|---|---|
| v1 | 2026-10-13 | Versión inicial (issue #1) |
| v1 | 2026-10-14 | Aclaraciones de la revisión (sin cambiar campos): `confidence` = softmax, desempate por `received_at`, expiración de `image_url` |
