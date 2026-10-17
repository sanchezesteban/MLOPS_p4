# Proyecto 4 — Modelo optimizado clasificando en edge

El modelo entrenado en el Proyecto 3 (ResNet-18, clases `cat` / `dog`) se optimiza a **ONNX INT8**,
clasifica **localmente** en una **Raspberry Pi Zero 2 W** con cámara USB, y cada captura (foto +
resultado) se envía a **AWS** y se muestra en la sección **«Capturas Edge»** del portal de los
Proyectos 1–3, desplegado en AWS.

```text
 best.pt (P3, r02) ──► ONNX FP32 ──► ONNX INT8 ──► Raspberry Pi Zero 2 W + Logitech C920
   SHA f759cde2…        convert.py    58effa03…     captura → recorte → 128×128 → inferencia local
                                                         │  POST /captures (SigV4, mismo capture_id
                                                         ▼  en reintentos)
                                              API Gateway → Lambda ingesta → S3 (foto) + DynamoDB
                                                         │  GET /captures (más reciente primero)
                                                         ▼
                                     Portal P1–P3 en EC2 → «Capturas Edge» (http://3.133.248.228)
```

**Equipo:** Esteban (PM) · Uriel (modelo y portal) · Juan Pablo (Raspberry Pi) · Ikram (AWS).
La ficha de entrega con todos los enlaces está en [`docs/p4/ficha-entrega.md`](docs/p4/ficha-entrega.md).

## Resultados

| Dato | Original (P3) | Optimizado | Fuente |
|---|---|---|---|
| Artefacto | `best.pt` PyTorch FP32 · SHA `f759cde2…` | ONNX INT8 · SHA `58effa03…` | `reports/p4/conversion_log.json` |
| Tamaño | 45 224 191 B (ONNX FP32) | 11 430 716 B | **−74.7 %** |
| Accuracy / F1 macro (val P3, 131) | 0.9618 / 0.9618 | 0.9618 / 0.9618 | **caída 0.00 pp** · `reports/p4/quality_metrics.json` |
| Latencia en la Pi p50 / p95 | 142.24 / 148.13 ms (FP32) | 70.18 / 71.62 ms | **2.03× más rápido** · `reports/p4/resources.json` |
| Mediciones | 10 calentamiento + 100 | 10 calentamiento + 100 | `reports/p4/benchmark.csv` |
| Capturas oficiales en AWS | — | 56 (31 cat, 25 dog) | `evidencias/aws/eventos.csv` |

Detalle: [calidad](docs/p4/quality-comparison.md) · [recursos](docs/p4/reporte-optimizacion.md) ·
[benchmark](docs/p4/benchmark-pi.md) · [estabilidad](docs/p4/estabilidad-procedimiento.md).

## Hardware y runtime

| Pieza | Valor |
|---|---|
| Dispositivo | Raspberry Pi Zero 2 W (4× Cortex-A53, 512 MB), microSD 32 GB |
| SO | Raspberry Pi OS Lite 64-bit (Debian 13), kernel 6.18 aarch64 |
| Cámara | Logitech C920 USB vía adaptador OTG micro-USB → USB-A (`/dev/video0`) |
| Runtime | Python 3.13.5 · onnxruntime 1.31.0 (CPU) · opencv-python-headless 5.0.0.93 · numpy 2.5.4 · pillow 12.3.0 · boto3 1.43.114 |
| Modelo desplegado | `resnet18-p3-v1.0.0-int8` (cuantización estática, QDQ, opset 17) |
| Entrada | 128×128 RGB, normalización ImageNet, clases `{0: cat, 1: dog}` |

Más detalle en [`docs/p4/hardware.md`](docs/p4/hardware.md).

## Estructura

```text
app/edge/            Conversión ONNX, comparación de calidad y reporte de recursos (laptop)
app/edge_ingest/     Lambdas de ingesta y lectura, simulador y evidencia de AWS
edge/                Programa de la Raspberry Pi: captura, inferencia, envío, benchmark
frontend/src/captures/  Sección «Capturas Edge» del portal
terraform/p4/        Infraestructura AWS del Proyecto 4
scripts/             Operación: fallo controlado de la ingesta y despliegue del portal
docs/p4/             Documentación y evidencia por ticket
reports/p4/          Resultados recalculables (CSV/JSON)
evidencias/aws/      Export de las capturas persistidas en AWS
```

El portal y el pipeline de los Proyectos 1–3 (`backend/`, `frontend/`, `app/`) siguen igual; su
documentación anterior está en [`docs/historico/README-proyectos-1-3.md`](docs/historico/README-proyectos-1-3.md)
(sus referencias a la cuenta AWS anterior no aplican).

## 1. Acceso a AWS

Cada integrante tiene su usuario IAM de mínimo privilegio; Ikram entrega la llave por privado.
Nunca se guardan llaves en el repositorio.

```bash
aws configure --profile mlops-p4          # región us-east-2
aws sts get-caller-identity --profile mlops-p4
```

Permisos, recursos y cómo reproducir la infraestructura (`terraform/p4/`): [`docs/p4/aws.md`](docs/p4/aws.md).

## 2. Recuperar el modelo y el dataset (DVC)

Desde la raíz del repo:

```bash
uv venv --python 3.12 .venv-dvc && uv pip install --python .venv-dvc 'dvc[s3]==3.67.1'
source .venv-dvc/bin/activate
dvc remote modify --local p4 profile mlops-p4
dvc pull    # best.pt, ONNX FP32/INT8, dataset y recortes v0.1.1
```

Verificar que es el modelo del Proyecto 3:

```bash
sha256sum models/p3/r02/best.pt                    # f759cde23fc314b63c4a4e3c20127ef1eb84121e579b04e7c97911ada20ab7d9
sha256sum models/p3/r02/onnx/model_int8.onnx       # 58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb
```

Procedencia completa: [`docs/p4/modelo-origen.md`](docs/p4/modelo-origen.md) y
[`docs/p4/artefactos.md`](docs/p4/artefactos.md).

## 3. Reproducir la optimización y la comparación de calidad

Requiere el `dvc pull` anterior.

```bash
cd app && uv sync --locked --no-build --group ml

# PyTorch → ONNX FP32 → ONNX INT8 (calibración solo con train; IDs en reports/p4/calibracion_ids.txt)
uv run --locked --no-build --group ml python edge/convert.py \
  --checkpoint ../models/p3/r02/best.pt \
  --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
  --crops-root ../data/derived/crops \
  --out-dir ../models/p3/r02/onnx --report-dir ../reports/p4

# Original vs. INT8 sobre el split val del P3 (131 recortes)
uv run --locked --no-build --group ml python edge/compare_quality.py \
  --checkpoint ../models/p3/r02/best.pt \
  --fp32 ../models/p3/r02/onnx/model_fp32.onnx \
  --int8 ../models/p3/r02/onnx/model_int8.onnx \
  --manifest ../data/derived/manifests/v0.1.1/manifest.csv \
  --crops-root ../data/derived/crops --report-dir ../reports/p4

# Reporte de recursos a partir del benchmark de la Pi
uv run --locked --no-build python edge/resource_report.py \
  --conversion-log ../reports/p4/conversion_log.json \
  --benchmark ../reports/p4/benchmark.csv \
  --output ../reports/p4/resources.json
```

Detalle: [`docs/p4/conversion-onnx.md`](docs/p4/conversion-onnx.md).

## 4. Preparar y arrancar la Raspberry Pi

En la Pi (Raspberry Pi OS Lite 64-bit, con la cámara conectada por el adaptador OTG):

```bash
python3 -m venv ~/edge-venv
cd ~/edge                                   # copia de la carpeta edge/ del repo
~/edge-venv/bin/python -m pip install -r requirements.txt
mkdir -p models                             # copiar aquí model_int8.onnx (y model_fp32.onnx para el benchmark)
cp config.example.json config.json          # cambiar "frame_source" a "camera"
aws configure --profile mlops-p4-device     # llave del usuario mlops-p4-device-rpi-zero2w-01 (por privado)
```

`config.json` está ignorado por Git. Define `device_id`, ruta y versión del modelo, recorte fijo
(`w`/`h` en 0 = sin recorte), modo (`interval` o `key`), intervalo, `api_url`, región y el
**nombre** del perfil AWS.

```bash
~/edge-venv/bin/python main.py --config config.json              # continuo (intervalo o Enter)
~/edge-venv/bin/python main.py --config config.json --once       # una captura
~/edge-venv/bin/python main.py --config config.json --retry <capture_id>
~/edge-venv/bin/python main.py --config config.json --retry-failed
~/edge-venv/bin/python benchmark.py --image validacion/000005_000004.jpg \
  --fp32 models/model_fp32.onnx --int8 models/model_int8.onnx --out benchmark.csv
```

Al arrancar imprime el SHA-256 del modelo cargado. Cada captura guarda `capturas/<capture_id>.jpg`
y `.json` (evento del contrato) **antes** de enviar; `capturas/log.jsonl` registra
`pendiente` / `enviado` / `error`, el error y `send_ms`. Sin red sigue clasificando; el envío
queda en `error` y se reintenta con el mismo `capture_id`. Detalle:
[`docs/p4/captura-inferencia.md`](docs/p4/captura-inferencia.md) y
[`docs/p4/envio-aws.md`](docs/p4/envio-aws.md).

## 5. Portal y «Capturas Edge»

- **URL:** http://3.133.248.228 → menú lateral **«Capturas Edge»** (`/captures`).
- Muestra foto, clase, confianza, fecha, `capture_id` completo, dispositivo, versión del modelo y
  recorte, de la más reciente a la más antigua, con botón «Actualizar».
- Lee `GET https://el1c2mr69k.execute-api.us-east-2.amazonaws.com/captures?limit=50`; la URL se
  inyecta al compilar (`VITE_CAPTURES_API_URL`). Sin ella, en producción muestra un error, nunca
  datos de ejemplo.

Operación del portal en AWS (requiere perfil administrador):

```bash
bash scripts/p4_portal.sh start | status | deploy main | stop
```

Desarrollo local del portal: `docker compose up --build` (ver el README histórico).
Detalle: [`docs/p4/capturas-edge.md`](docs/p4/capturas-edge.md) y
[`docs/p4/capturas-api-real.md`](docs/p4/capturas-api-real.md).

## 6. Verificar el recorrido

| Comprobación | Cómo |
|---|---|
| Una captura llegó a la API del portal | `bash edge/verificar_captura.sh <capture_id>` |
| Una captura está persistida en AWS | `cd app && uv run python -m edge_ingest.evidence --profile mlops-p4 get <capture_id> --download foto.jpg` |
| Exportar todas las capturas | `uv run python -m edge_ingest.evidence --profile mlops-p4 export --out ../evidencias/aws` |
| Sin red sigue clasificando | `bash edge/sin_red_demo.sh 65` en la Pi (ver [`docs/p4/validacion-pi.md`](docs/p4/validacion-pi.md)) |
| Fallo de envío y reintento sin duplicados | `bash scripts/p4_ingesta_fallo.sh off` → captura → `on` → `--retry-failed` |

Lista completa con resultados: [`docs/p4/verificacion-manual.md`](docs/p4/verificacion-manual.md).

## 7. Pruebas automatizadas

```bash
cd app && uv run pytest tests/test_edge_ingest.py tests/test_edge_read_api.py \
  tests/test_edge_evidence.py tests/test_resource_report.py
cd edge && python -m pytest test_preprocess.py
cd frontend && npm ci && npm test
```

## Configuración y secretos

- Plantillas sin secretos: `edge/config.example.json`, `frontend/.env.example`,
  `terraform/p4/terraform.tfvars.example`.
- Llaves AWS solo en perfiles locales (`~/.aws/credentials`); `.env`, `config.json`,
  `.dvc/config.local` y `*.tfvars` están ignorados por Git.
- El acceso de evaluación es un usuario de solo lectura que vence el 2026-11-17; su contraseña
  se entrega por privado, no está en el repositorio.

## Documentación por tema

| Tema | Documento |
|---|---|
| Contrato del evento (Pi ↔ AWS ↔ portal) | [`docs/p4/contrato-evento.md`](docs/p4/contrato-evento.md) |
| Modelo de origen y artefactos | [`modelo-origen.md`](docs/p4/modelo-origen.md) · [`artefactos.md`](docs/p4/artefactos.md) |
| Optimización y calidad | [`conversion-onnx.md`](docs/p4/conversion-onnx.md) · [`quality-comparison.md`](docs/p4/quality-comparison.md) |
| Recursos | [`benchmark-pi.md`](docs/p4/benchmark-pi.md) · [`reporte-optimizacion.md`](docs/p4/reporte-optimizacion.md) |
| Dispositivo | [`hardware.md`](docs/p4/hardware.md) · [`captura-inferencia.md`](docs/p4/captura-inferencia.md) · [`validacion-pi.md`](docs/p4/validacion-pi.md) |
| Envío y estabilidad | [`envio-aws.md`](docs/p4/envio-aws.md) · [`estabilidad-procedimiento.md`](docs/p4/estabilidad-procedimiento.md) |
| AWS | [`aws.md`](docs/p4/aws.md) |
| Portal | [`capturas-edge.md`](docs/p4/capturas-edge.md) · [`capturas-api-real.md`](docs/p4/capturas-api-real.md) |
| Entrega | [`ficha-entrega.md`](docs/p4/ficha-entrega.md) · [`verificacion-manual.md`](docs/p4/verificacion-manual.md) · [`guion-demo.md`](docs/p4/guion-demo.md) |
