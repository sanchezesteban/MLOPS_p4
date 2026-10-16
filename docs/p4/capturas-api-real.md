# P4-15 — «Capturas Edge» conectada a la API de lectura real

**Issue:** [#15](https://github.com/sanchezesteban/MLOPS_p4/issues/15) · **Responsable:** Uriel (@urielpinag)
**Ámbito:** rúbrica 5.2, compuerta **M3**.

## Cómo quedó conectada

La sección «Capturas Edge» (PR #38) lee la URL desde `VITE_CAPTURES_API_URL`; el despliegue de AWS (infra #18, PR #36/#44) compila el frontend con:

```text
VITE_CAPTURES_API_URL = https://el1c2mr69k.execute-api.us-east-2.amazonaws.com
```

Ese valor queda inlinado en el bundle desplegado (el `grep` del `index-*.js` lo confirma y **no** contiene `sample.json`: en producción nunca hay datos de ejemplo). El CORS de `GET /captures` incluye el origen del portal (`http://3.133.248.228`).

## Verificación contra AWS — captura oficial `8d026b3c-08ed-4770-9632-0ecd2d38b843`

La captura del reinicio coincide en las tres vistas independientes: lo que muestra el portal, lo que responde `GET /captures` y la **evidencia exportada de AWS** (`evidencias/aws/eventos.json`, del frente AWS #19):

| Campo | Portal (captura de pantalla) | `GET /captures` | Evidencia AWS (`eventos.json`) |
|---|---|---|---|
| `capture_id` | `8d026b3c-08ed-4770-9632-0ecd2d38b843` | ✅ | ✅ |
| clase | Gato | `cat` | `cat` |
| confianza | 88 % | `0.8809` | `0.8809` |
| `captured_at` | 16 oct, 12:50 p.m. | `2026-10-16T12:50:29.216253-06:00` | ✅ (UTC `18:50:29.216Z`) |
| `received_at` | — | `2026-10-16T18:50:29.983Z` | ✅ |
| `device_id` | `rpi-zero2w-01` | ✅ | ✅ |
| `model_version` | `resnet18-p3-v1.0.0-int8` | ✅ | ✅ |
| `model_sha256` | — (en el contrato) | `58effa03…` (nuestro ONNX INT8, #7) | ✅ |
| `crop` | «sin recorte» | `null` | columnas `crop_*` vacías |
| imagen | (miniatura) | URL firmada de S3 | `image_in_s3: true`, `image_bytes: 18503`, `image_version_id: UMBbM1UDWiJW_NcTCHsYl1_wUjMTq7RA` |

Los mismos valores están en `evidencias/aws/eventos.csv` (misma fila, primera del archivo).

## «Una captura nueva aparece al presionar Actualizar»

El botón re-consulta `GET /captures`. La captura oficial es de las **12:50**, y para las **13:45** la Pi ya había enviado nuevas (`06afc6ca-…` y `44efeb65-…`): al refrescar, el portal las muestra arriba y desplaza a la anterior — la lista refleja el estado real de AWS (56 eventos en la exportación). Orden siempre de la más reciente a la más antigua.

## Error de red con mensaje útil

En producción sin API configurada la sección muestra «API de capturas no configurada.» y ante fallos de red muestra el estado de error con «Reintentar» (evidencia: `docs/p4/capturas-edge-sin-api.png`, PR #38).

## Evidencia

![Portal desplegado con la captura oficial de la Pi](capturas-edge-real.png)
