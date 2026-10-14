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

La API de ingesta (#16) debe usar autorización **AWS_IAM** en `POST /captures`; la Pi firma
cada petición (SigV4) con su credencial. El rol de solo lectura para el evaluador va en #19.

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
