# P4-04 — Cuenta AWS del Proyecto 4

**Issue:** [#4](https://github.com/sanchezesteban/MLOPS_p4/issues/4) · **Responsable:** Ikram (@ikramzaldivar)
**Rúbrica:** 6.3 (configuración operable y acceso controlado); base de 4.2, 5.1 y M3.

Los buckets del Proyecto 3 (`…-222629887955`) viven en una cuenta ajena al equipo actual,
así que el P4 usa una cuenta propia. Toda la infraestructura de este issue está en
Terraform (`terraform/p4/`) y no contiene secretos: las access keys se generan fuera de
Terraform y se entregan por privado.

## Recursos

| Recurso | Nombre | Uso |
|---|---|---|
| Cuenta / región | `595981034933` · `us-east-2` | Todo el P4 |
| Bucket de modelos | `mlops-p4-models-595981034933` | Remote DVC: `best.pt`, ONNX FP32/INT8 y dataset (#7) |
| Bucket de capturas | `mlops-p4-captures-595981034933` | Fotografías de la Pi, clave `captures/AAAA/MM/DD/<capture_id>.jpg` (#16) |
| Tabla DynamoDB | `mlops-p4-captures` | Metadatos del evento; llave `capture_id` (#16, #17) |
| Índice | `by_captured_at` (`gsi_pk` + `captured_at_utc`) | Listar de la más reciente a la más antigua (#17) |
| Grupo IAM | `mlops-p4-team` | Política de mínimo privilegio del equipo |
| Usuarios del equipo | `mlops-p4-uriel`, `mlops-p4-juanpablo`, `mlops-p4-esteban` | CLI/DVC, sin consola |
| Usuario del dispositivo | `mlops-p4-device-rpi-zero2w-01` | Solo `POST /captures` |
| Presupuesto | `mlops-p4-mensual` · USD 10 | Correo al 80 % real y al 100 % pronosticado |
| State de Terraform | `s3://proyecto2-prod-tfstate-595981034933/p4/terraform.tfstate` | Versionado, bloqueo nativo de S3 |

Los dos buckets tienen versionado, cifrado SSE-S3, bloqueo total de acceso público,
`BucketOwnerEnforced` y una política que deniega cualquier petición sin HTTPS.
La tabla es on-demand, cifrada, con recuperación a un punto en el tiempo (PITR) y
protección contra borrado.

### Contrato con la ingesta (#16) y la lectura (#17)

- Escritura con `ConditionExpression: attribute_not_exists(capture_id)`: un reintento con el
  mismo `capture_id` no duplica (criterio 4.3).
- Cada ítem guarda `gsi_pk = "capture"` y `captured_at_utc` (el `captured_at` del contrato
  convertido a UTC en ISO-8601). `captured_at` conserva la zona horaria original; no se usa
  como llave porque con zonas distintas no ordena bien como texto.
- `GET /captures` consulta `by_captured_at` con `ScanIndexForward = false`.

## Permisos

| Quién | Puede | No puede |
|---|---|---|
| Equipo (`mlops-p4-team`) | Leer y subir en el bucket de modelos (DVC push/pull); leer capturas y la tabla | Borrar modelos, escribir capturas o la tabla, administrar IAM |
| Pi (`mlops-p4-device-…`) | `execute-api:Invoke` sobre `*/*/POST/captures` de esta cuenta y región | Leer (`GET`), escribir directo en S3/DynamoDB |
| Ikram | Administración de la cuenta (aplicar Terraform) | — |
| Evaluador (`mlops-p4-evaluador`) | Leer los dos buckets, la tabla, los logs de la ingesta y la API, y la configuración de la Lambda (hasta el 2026-11-15 UTC) | Escribir, borrar, cambiar la Lambda o administrar IAM |

La API de ingesta (#16) debe usar autorización **AWS_IAM** en `POST /captures`; la Pi firma
cada petición (SigV4) con su credencial. El acceso de solo lectura del evaluador se describe en «Acceso de evaluación».

Comprobado con el simulador de políticas de IAM (`aws iam simulate-principal-policy`) tras el `apply`:

```text
mlops-p4-uriel
  s3:PutObject   models/*                  allowed
  s3:GetObject   models/*                  allowed
  s3:DeleteObject models/*                 implicitDeny
  s3:GetObject   captures/*                allowed
  s3:PutObject   captures/*                implicitDeny
  dynamodb:Query index/by_captured_at      allowed
  dynamodb:PutItem table                   implicitDeny
  iam:CreateUser                           implicitDeny
mlops-p4-device-rpi-zero2w-01
  execute-api:Invoke …/POST/captures       allowed
  execute-api:Invoke …/GET/captures        implicitDeny
  s3:PutObject   captures/*                implicitDeny
  dynamodb:PutItem table                   implicitDeny
```

## Acceso de cada integrante

Ikram genera la llave de cada usuario y la entrega por mensaje privado (nunca en Git, issues ni chats de grupo):

```bash
aws iam create-access-key --user-name mlops-p4-uriel
```

Cada integrante la guarda en un perfil propio:

```bash
aws configure --profile mlops-p4      # región us-east-2, salida json
aws sts get-caller-identity --profile mlops-p4
# → arn:aws:iam::595981034933:user/mlops-p4/mlops-p4-<nombre>
```

### Remote DVC (para #7)

```bash
dvc remote add -d p4 s3://mlops-p4-models-595981034933/dvc
dvc remote modify p4 region us-east-2
dvc remote modify --local p4 profile mlops-p4   # va a .dvc/config.local, ignorado por Git
dvc push
```

La Pi recibe su llave igual, en el archivo de configuración local ignorado por Git (plantilla en #19).

## Reproducir o modificar

Requisitos: Terraform ≥ 1.10 y credenciales de administrador de la cuenta.

```bash
cd terraform/p4
cp terraform.tfvars.example terraform.tfvars   # correo(s) de la alerta de presupuesto
terraform init
terraform plan
terraform apply
terraform output
```

Primer `apply` (2026-10-13): `Resources: 24 added, 0 changed, 0 destroyed.`

## Ingesta de capturas (#16)

`POST https://el1c2mr69k.execute-api.us-east-2.amazonaws.com/captures`, con autorización
**AWS_IAM**: cada petición va firmada con SigV4 (servicio `execute-api`, región `us-east-2`).
Sin firma, la API responde `403`.

| Pieza | Recurso | Código |
|---|---|---|
| API HTTP | `mlops-p4-captures` (stage `$default`, límite 10 req/s y ráfaga de 20) | `terraform/p4/ingest.tf` |
| Lambda | `mlops-p4-ingest` (Python 3.12, solo boto3) | `app/edge_ingest/handler.py` |
| Rol de la Lambda | `s3:PutObject` en `captures/*`; `dynamodb:GetItem`/`PutItem` en la tabla | `terraform/p4/ingest.tf` |
| Logs | `/aws/lambda/mlops-p4-ingest` y `/aws/apigateway/mlops-p4-captures` (30 días) | `terraform/p4/ingest.tf` |
| Simulador | Envía eventos del contrato v1 firmados como la Pi | `app/edge_ingest/simulate.py` |
| Fallo controlado | Apaga y prende la ingesta sin tocar datos | `scripts/p4_ingesta_fallo.sh` |

La ingesta:

1. Valida todos los campos del contrato v1 y rechaza campos desconocidos. Si algo está mal,
   responde `400` con `{"error", "field"}` (por ejemplo, `confidence` fuera de 0–1, una fecha
   sin zona horaria o una imagen que no es JPEG o supera 1 MB).
2. Si el `capture_id` ya existe, responde `200` con `"duplicate": true` y no escribe nada.
3. Guarda el JPEG en `captures/AAAA/MM/DD/<capture_id>.jpg`, con la fecha UTC de `captured_at`.
   La clave es determinista: un reintento escribe el mismo objeto.
4. Escribe los metadatos con `attribute_not_exists(capture_id)` y agrega `received_at`,
   `image_key`, `captured_at_utc` y `gsi_pk`. Responde `201`.
5. Ante una falla interna responde `500`, y la Pi reintenta con el mismo `capture_id`.

Pruebas sin AWS (S3 y DynamoDB falsos): `cd app && uv run pytest tests/test_edge_ingest.py`
(25 casos).

### Simulador

La Pi y el simulador usan la llave de `mlops-p4-device-rpi-zero2w-01`, en un perfil local:

```bash
cd app
uv run python -m edge_ingest.simulate \
  --url https://el1c2mr69k.execute-api.us-east-2.amazonaws.com \
  --profile mlops-p4-device --count 4                 # 4 capturas nuevas (cat/dog)
uv run python -m edge_ingest.simulate --url … --profile mlops-p4-device --count 1 --repeat 3
uv run python -m edge_ingest.simulate --url … --profile mlops-p4-device --image foto.jpg --label dog
```

`--log salida.jsonl` guarda cada envío (sin la imagen) con su estado y su `send_ms`.

Resultado contra la API real (2026-10-14 UTC):

```text
dda0ea54-… cat intento=1 -> 201 {"…", "duplicate": false} (546.4 ms)
515ea6ad-… dog intento=1 -> 201 {"…", "duplicate": false} (408.0 ms)
fbd60756-… cat intento=1 -> 201 {"received_at": "2026-10-14T04:28:04.317Z", "duplicate": false}
fbd60756-… cat intento=2 -> 200 {"received_at": "2026-10-14T04:28:04.317Z", "duplicate": true}
fbd60756-… cat intento=3 -> 200 {"received_at": "2026-10-14T04:28:04.317Z", "duplicate": true}
confidence = 1.5         -> 400 {"error": "debe ser un número entre 0 y 1", "field": "confidence"}
```

La tabla queda con un solo registro para `fbd60756-…`, y el JPEG tiene una sola versión en S3
(no se sobrescribió).

### Fallo controlado y reintento (criterio 4.3)

```bash
AWS_PROFILE=<admin> bash scripts/p4_ingesta_fallo.sh off     # concurrencia de la Lambda = 0
# la Pi envía → 503; la captura queda con send_status = error
AWS_PROFILE=<admin> bash scripts/p4_ingesta_fallo.sh on      # quita la reserva
# la Pi reintenta el mismo capture_id → 201; un segundo reintento → 200 duplicate
```

Ensayado el 2026-10-14 (UTC) con `bdd524df-535e-43bd-b76e-db3e5f974403`: `503` → `201` → `200`
(`duplicate: true`), con 1 registro en DynamoDB y 1 versión de la imagen. El access log de la
API registra el `503`. Prender y apagar no deja diferencias en Terraform
(`terraform plan` → `No changes`).

### Consultas de solo lectura

```bash
aws dynamodb get-item --table-name mlops-p4-captures --region us-east-2 \
  --key '{"capture_id":{"S":"<capture_id>"}}'
aws dynamodb query --table-name mlops-p4-captures --region us-east-2 \
  --index-name by_captured_at --key-condition-expression "gsi_pk = :p" \
  --expression-attribute-values '{":p":{"S":"capture"}}' --no-scan-index-forward
aws s3api head-object --bucket mlops-p4-captures-595981034933 --region us-east-2 \
  --key captures/AAAA/MM/DD/<capture_id>.jpg
```

Las capturas del simulador llevan `device_id = simulador-laptop` (cámbialo con `--device-id`)
y una imagen sintética con el texto `SIMULADOR`. Así no se confunden con las de la Pi y se
borran antes de la entrega con `evidence.py cleanup` (ver «Evidencia para la entrega»).

## Acceso de evaluación (#19)

Usuario `mlops-p4-evaluador` (`terraform/p4/evaluator.tf`), con la política administrada
`mlops-p4-evaluador-solo-lectura`. Cada permiso lleva la condición
`aws:CurrentTime < evaluator_access_until` (por defecto `2026-11-15T23:59:59Z`): al pasar la
fecha deja de funcionar aunque nadie lo borre.

- **Consola:** `https://595981034933.signin.aws.amazon.com/console`, región `us-east-2`.
  Ikram crea la contraseña en IAM y la entrega por privado; no se publica.
- **Qué puede ver:** objetos y versiones de los dos buckets, la tabla `mlops-p4-captures` y su
  índice, los logs `/aws/lambda/mlops-p4-ingest`, `/aws/lambda/mlops-p4-read` y
  `/aws/apigateway/mlops-p4-captures`, y la configuración y concurrencia de las Lambdas (para ver si el fallo controlado está activo).
- **Qué no puede hacer:** escribir, borrar, cambiar la Lambda o la API, ni administrar IAM.

Comprobado con `aws iam simulate-principal-policy`, con la fecha simulada antes y después de la expiración:

```text
s3:GetObject / s3:ListBucket (capturas y modelos)    allowed
dynamodb:Query / GetItem                              allowed
logs:FilterLogEvents (API)                            allowed
lambda:GetFunctionConcurrency                         allowed
s3:PutObject / s3:DeleteObject                        implicitDeny
dynamodb:PutItem / DeleteItem                         implicitDeny
lambda:PutFunctionConcurrency                         implicitDeny
iam:CreateUser                                        implicitDeny
s3:GetObject después del 2026-11-15                   implicitDeny
```

Para alargar o acortar el acceso: `terraform apply -var 'evaluator_access_until=AAAA-MM-DDT23:59:59Z'`.

## API de lectura para el portal (#17)

`GET https://el1c2mr69k.execute-api.us-east-2.amazonaws.com/captures?limit=50`

- **Sin firma**, para que el navegador del portal la consulte directamente. Es de solo lectura
  y tiene el mismo tope de tráfico de la API (10 req/s, ráfaga de 20).
- **CORS** solo para `portal_origins`: por ahora `http://localhost:8080` (docker compose) y
  `http://localhost:5173` (vite dev). Cuando el portal esté en AWS (#18) se agrega su URL.
- **Orden:** de la más reciente a la más antigua (índice `by_captured_at`,
  `ScanIndexForward = false`).
- **`limit`:** de 1 a 100 (50 por defecto). Fuera de rango → `400 {"error", "field": "limit"}`.
- Cada elemento trae los campos del contrato v1 más `image_url`, una URL firmada de S3 válida
  15 minutos. No se exponen `gsi_pk` ni `captured_at_utc`. Respuesta con `Cache-Control: no-store`.
- Lambda `mlops-p4-read` (`app/edge_ingest/read_api.py`). Su rol solo puede consultar el índice
  y leer `captures/*` para firmar las URL; no escribe nada.

```json
{
  "items": [
    {
      "capture_id": "bdd524df-535e-43bd-b76e-db3e5f974403",
      "captured_at": "2026-10-13T22:30:38-06:00",
      "received_at": "2026-10-14T04:30:46.677Z",
      "device_id": "rpi-zero2w-01",
      "model_version": "resnet18-p3-v1.0.0-int8",
      "model_sha256": "58effa03a01cf847bb9a94a96c30247220b47bb394715949e404450ca4d9a1bb",
      "predicted_class": "dog",
      "confidence": 0.6278,
      "latency_ms": 486.9,
      "crop": { "x": 80, "y": 40, "w": 480, "h": 400 },
      "image_key": "captures/2026/10/14/bdd524df-535e-43bd-b76e-db3e5f974403.jpg",
      "image_url": "https://mlops-p4-captures-595981034933.s3.us-east-2.amazonaws.com/captures/…?X-Amz-…"
    }
  ]
}
```

(Respuesta real; `image_url` está recortada.)

Pruebas sin AWS: `cd app && uv run pytest tests/test_edge_read_api.py` (9 casos). Contra la API real:

```text
GET ?limit=3                      → 200, 3 capturas de la más reciente a la más antigua, 12 campos cada una
GET image_url                     → 200 image/jpeg (la foto de la captura bdd524df…)
GET ?limit=500                    → 400 {"field": "limit"}
OPTIONS con Origin localhost:8080 → 204, access-control-allow-origin: http://localhost:8080
GET con Origin ajeno              → sin access-control-allow-origin (el navegador lo bloquea)
POST /captures sin firma          → 403 (la ingesta sigue protegida)
```

Desde el portal (#15):

```ts
const res = await fetch(`${import.meta.env.VITE_CAPTURES_API_URL}/captures?limit=50`);
if (!res.ok) throw new Error((await res.json()).error);
const { items } = await res.json(); // ya vienen de la más reciente a la más antigua
```

## Evidencia para la entrega (#19)

`app/edge_ingest/evidence.py` sirve al equipo y al evaluador. Las consultas son de solo
lectura y cada quien las corre con su propio perfil (`mlops-p4` o el del evaluador):

```bash
cd app
# Una captura: metadatos en DynamoDB + objeto en S3 (versión, tamaño, fecha) y, opcionalmente, la foto.
uv run python -m edge_ingest.evidence --profile mlops-p4 get <capture_id> --download foto.jpg

# Todas las capturas, de la más reciente a la más antigua → evidencias/aws/eventos.csv y eventos.json
uv run python -m edge_ingest.evidence --profile mlops-p4 export --out ../evidencias/aws
```

`export` imprime un resumen: total de eventos, conteo por clase y por dispositivo, y las
capturas cuya imagen falta en S3. El CSV trae una fila por evento con los campos del contrato,
`captured_at_utc`, el recorte separado en columnas y, de S3, `image_in_s3`, `image_bytes`,
`image_version_id` e `image_last_modified`.

Prueba contra AWS (2026-10-14): `get` del evento `bdd524df…` devolvió sus metadatos, la versión
`k9YHvxeX…` de su imagen (15 202 B) y la descargó. `get` de un ID inexistente sale con código 1.
`export` escribió 8 eventos sin imágenes faltantes.

### Limpieza de capturas de prueba

Requiere un perfil administrador. Borra los metadatos y **todas las versiones** de la imagen de
un `device_id`. Sin `--confirm` solo lista lo que borraría:

```bash
uv run python -m edge_ingest.evidence --profile <admin> cleanup --device-id simulador-laptop
uv run python -m edge_ingest.evidence --profile <admin> cleanup --device-id simulador-laptop --confirm
```

Las 8 capturas del primer ensayo del simulador (2026-10-14 04:27–04:30 UTC) se enviaron antes
de que el simulador tuviera `device_id` propio, así que quedaron como `rpi-zero2w-01`. Se borraron
el 2026-10-14 con `cleanup --device-id rpi-zero2w-01 --confirm`; la tabla y el bucket quedaron vacíos
para las capturas reales de la Pi.

### Configuración de la Pi sin secretos

Plantilla: `app/edge/.env.pi.example`. Se copia a `app/edge/.env.pi`, que Git ignora por el
patrón `.env.*`. Incluye `DEVICE_ID`, la ruta y el SHA-256 del modelo INT8, el recorte, el
intervalo de captura, la URL de la API y el **nombre** del perfil AWS. La llave se configura con
`aws configure --profile mlops-p4-device` y nunca va en el archivo.

## Portal en AWS (#18)

**URL:** `http://3.133.248.228` (IP elástica: no cambia al apagar y prender la instancia).

La rúbrica (5.1, M3) pide que «Capturas Edge» esté en la navegación del portal de P1–P3
**desplegado en AWS**. El portal solo corría con `docker compose` local, así que se despliega
en una EC2 con el mismo compose (`terraform/p4/portal.tf`):

| Pieza | Valor |
|---|---|
| Instancia | `mlops-p4-portal`, `t3.small`, Ubuntu 24.04, disco gp3 de 30 GB cifrado, IMDSv2, 4 GB de swap |
| Red | VPC por defecto (`us-east-2a`); security group solo con **HTTP 80** de entrada |
| Administración | SSM Session Manager (rol `AmazonSSMManagedInstanceCore`); sin SSH ni llaves |
| Servicios | `frontend` (nginx, puerto 80), `backend`, `mariadb`, `minio`, `copilot` — `restart: unless-stopped` |
| Fuera de alcance | `trainer-worker`, `ml-api`, `mlflow` (entrenamiento del P3 con PyTorch; el P4 no lo recalifica). Sus secciones responden 502 |
| Secretos | Contraseñas de MariaDB y MinIO generadas en la instancia (`/opt/portal/.env`, modo 600); no están en Terraform ni en Git. Copilot sin `ANTHROPIC_API_KEY` responde 503 |
| MinIO | `minio/minio` y `quay.io/minio/minio` ya no se pueden descargar; en AWS se usa `cgr.dev/chainguard/minio` (mismo comando y variables), solo en el override de la EC2 |
| «Capturas Edge» | El frontend se compila con `VITE_CAPTURES_API_URL` = URL de la API; el CORS de `GET /captures` incluye `http://3.133.248.228` |

Al arrancar por primera vez, la instancia instala Docker, clona `main` y ejecuta
`/usr/local/bin/portal-deploy` (`git pull` + `docker compose up -d --build` de esos servicios).
El log queda en `/var/log/portal-bootstrap.log`.

### Operación

```bash
AWS_PROFILE=<admin> bash scripts/p4_portal.sh deploy main   # actualizar tras un merge (p. ej. #15)
AWS_PROFILE=<admin> bash scripts/p4_portal.sh status        # EC2 + contenedores + commit desplegado
AWS_PROFILE=<admin> bash scripts/p4_portal.sh logs          # log de arranque
AWS_PROFILE=<admin> bash scripts/p4_portal.sh stop          # apagar fuera de la demo (ahorra cómputo)
AWS_PROFILE=<admin> bash scripts/p4_portal.sh start         # prender antes de la demo (~1 min)
```

Comprobado el 2026-10-14: `/` y `/api/health` → 200, `/reports/quality.json` → 200, `/ml-api/` → 502
(fuera de alcance). Tras reiniciar la EC2, el portal volvió solo en ~45 s.

Costo aproximado: `t3.small` ≈ USD 0.02/h encendida + IP pública ≈ USD 0.005/h + 30 GB gp3
≈ USD 2.4/mes. Apagada solo cuesta el disco y la IP.
