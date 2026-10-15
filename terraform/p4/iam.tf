# Usuarios IAM sin consola ni llaves: las access keys se crean fuera de Terraform
# (consola o `aws iam create-access-key`) para que ningún secreto quede en el state.

locals {
  models_arn   = aws_s3_bucket.this["models"].arn
  captures_arn = aws_s3_bucket.this["captures"].arn
}

# --- Integrantes del equipo -------------------------------------------------

resource "aws_iam_group" "team" {
  name = "${var.name_prefix}-team"
  path = "/${var.name_prefix}/"
}

resource "aws_iam_user" "team" {
  for_each = var.team_members

  name = "${var.name_prefix}-${each.key}"
  path = "/${var.name_prefix}/"
}

resource "aws_iam_user_group_membership" "team" {
  for_each = aws_iam_user.team

  user   = each.value.name
  groups = [aws_iam_group.team.name]
}

data "aws_iam_policy_document" "team" {
  # DVC push/pull de modelos y dataset (#7). Sin DeleteObject: el versionado y
  # la ausencia de borrado protegen los artefactos publicados.
  statement {
    sid       = "ModelsList"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [local.models_arn]
  }

  statement {
    sid = "ModelsReadWrite"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${local.models_arn}/*"]
  }

  # Lectura de capturas y metadatos para depurar Pi, ingesta y portal.
  statement {
    sid       = "CapturesRead"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject"]
    resources = [local.captures_arn, "${local.captures_arn}/*"]
  }

  statement {
    sid = "CapturesTableRead"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.captures.arn,
      "${aws_dynamodb_table.captures.arn}/index/*",
    ]
  }
}

resource "aws_iam_group_policy" "team" {
  name   = "${var.name_prefix}-team-least-privilege"
  group  = aws_iam_group.team.name
  policy = data.aws_iam_policy_document.team.json
}

# --- Dispositivo edge ---------------------------------------------------------

# La Pi solo puede invocar `POST /captures` (contrato v1). La API de ingesta (#16)
# debe usar autorización AWS_IAM en esa ruta; el comodín de API id permite crearla
# después sin tocar esta política, pero sigue limitado a esta cuenta, región, método y ruta.
resource "aws_iam_user" "device" {
  name = "${var.name_prefix}-device-${var.device_id}"
  path = "/${var.name_prefix}/"
}

data "aws_iam_policy_document" "device" {
  statement {
    sid       = "PostCapturesOnly"
    actions   = ["execute-api:Invoke"]
    resources = ["arn:aws:execute-api:${var.region}:${local.account_id}:*/*/POST/captures"]
  }
}

resource "aws_iam_user_policy" "device" {
  name   = "${var.name_prefix}-device-post-captures"
  user   = aws_iam_user.device.name
  policy = data.aws_iam_policy_document.device.json
}
