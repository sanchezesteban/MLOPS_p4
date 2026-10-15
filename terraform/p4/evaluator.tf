# Acceso de evaluación (#19, rúbrica 4.2 y 6.3): usuario de solo lectura para el
# profesor, con fecha de expiración en la política. Puede comprobar que las capturas
# y los artefactos están realmente en AWS, pero no puede escribir, borrar ni cambiar
# permisos. La contraseña de consola y las llaves se crean fuera de Terraform.

resource "aws_iam_user" "evaluator" {
  name = "${var.name_prefix}-evaluador"
  path = "/${var.name_prefix}/"

  # La consola guarda la descripción de cada access key como etiqueta del usuario;
  # Terraform no las administra.
  lifecycle {
    ignore_changes = [tags]
  }
}

data "aws_iam_policy_document" "evaluator" {
  # Navegar en la consola: listar buckets, tablas y grupos de logs.
  statement {
    sid = "ConsoleListing"
    actions = [
      "s3:ListAllMyBuckets",
      "dynamodb:ListTables",
      "logs:DescribeLogGroups",
      "lambda:ListFunctions",
      "apigateway:GET",
    ]
    resources = ["*"]
    condition {
      test     = "DateLessThan"
      variable = "aws:CurrentTime"
      values   = [var.evaluator_access_until]
    }
  }

  statement {
    sid = "ReadBuckets"
    actions = [
      "s3:ListBucket",
      "s3:ListBucketVersions",
      "s3:GetBucketLocation",
      "s3:GetBucketVersioning",
      "s3:GetEncryptionConfiguration",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = [
      local.models_arn,
      "${local.models_arn}/*",
      local.captures_arn,
      "${local.captures_arn}/*",
    ]
    condition {
      test     = "DateLessThan"
      variable = "aws:CurrentTime"
      values   = [var.evaluator_access_until]
    }
  }

  statement {
    sid = "ReadCapturesTable"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:DescribeContinuousBackups",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.captures.arn,
      "${aws_dynamodb_table.captures.arn}/index/*",
    ]
    condition {
      test     = "DateLessThan"
      variable = "aws:CurrentTime"
      values   = [var.evaluator_access_until]
    }
  }

  # Logs de la ingesta y de la API (envíos, duplicados y fallo controlado).
  statement {
    sid = "ReadIngestLogs"
    actions = [
      "logs:DescribeLogStreams",
      "logs:GetLogEvents",
      "logs:FilterLogEvents",
      "logs:StartQuery",
    ]
    resources = [
      "${aws_cloudwatch_log_group.ingest.arn}:*",
      "${aws_cloudwatch_log_group.api.arn}:*",
      "${aws_cloudwatch_log_group.read.arn}:*",
    ]
    condition {
      test     = "DateLessThan"
      variable = "aws:CurrentTime"
      values   = [var.evaluator_access_until]
    }
  }

  statement {
    sid       = "ReadQueryResults"
    actions   = ["logs:GetQueryResults", "logs:StopQuery"]
    resources = ["*"]
    condition {
      test     = "DateLessThan"
      variable = "aws:CurrentTime"
      values   = [var.evaluator_access_until]
    }
  }

  # Configuración de la Lambda (incluye ver si el fallo controlado está activo).
  statement {
    sid = "ReadIngestFunction"
    actions = [
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionConcurrency",
    ]
    resources = [aws_lambda_function.ingest.arn, aws_lambda_function.read.arn]
    condition {
      test     = "DateLessThan"
      variable = "aws:CurrentTime"
      values   = [var.evaluator_access_until]
    }
  }

  # Cambiar su propia contraseña si se le pide al primer inicio de sesión.
  statement {
    sid       = "OwnPassword"
    actions   = ["iam:ChangePassword", "iam:GetUser"]
    resources = [aws_iam_user.evaluator.arn]
  }

  statement {
    sid       = "PasswordPolicy"
    actions   = ["iam:GetAccountPasswordPolicy"]
    resources = ["*"]
  }
}

# Política administrada: una política en línea de usuario se limita a 2048 bytes.
resource "aws_iam_policy" "evaluator" {
  name   = "${var.name_prefix}-evaluador-solo-lectura"
  path   = "/${var.name_prefix}/"
  policy = data.aws_iam_policy_document.evaluator.json
}

resource "aws_iam_user_policy_attachment" "evaluator" {
  user       = aws_iam_user.evaluator.name
  policy_arn = aws_iam_policy.evaluator.arn
}
