# Ingesta de capturas (#16): API Gateway HTTP → Lambda → S3 + DynamoDB.
# `POST /captures` exige SigV4 (AWS_IAM); solo el usuario de la Pi tiene permiso (iam.tf).

data "archive_file" "ingest" {
  type        = "zip"
  source_file = "${path.module}/../../app/edge_ingest/handler.py"
  output_path = "${path.module}/build/ingest.zip"
}

resource "aws_iam_role" "ingest" {
  name = "${var.name_prefix}-ingest-lambda"
  path = "/${var.name_prefix}/"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "WriteCaptureImages"
    actions   = ["s3:PutObject"]
    resources = ["${local.captures_arn}/captures/*"]
  }

  statement {
    sid       = "ConditionalWriteMetadata"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.captures.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest.arn}:*"]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "${var.name_prefix}-ingest"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${var.name_prefix}-ingest"
  retention_in_days = 30
}

resource "aws_lambda_function" "ingest" {
  function_name    = "${var.name_prefix}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      CAPTURES_BUCKET = aws_s3_bucket.this["captures"].id
      CAPTURES_TABLE  = aws_dynamodb_table.captures.name
    }
  }

  depends_on = [aws_iam_role_policy.ingest, aws_cloudwatch_log_group.ingest]
}

resource "aws_apigatewayv2_api" "captures" {
  name          = "${var.name_prefix}-captures"
  protocol_type = "HTTP"

  # El portal consulta `GET /captures` desde el navegador (#17). `POST` no lo usa ningún
  # navegador: la Pi firma con SigV4 y CORS no aplica.
  cors_configuration {
    allow_origins = concat(var.portal_origins, ["http://${aws_eip.portal.public_ip}"])
    allow_methods = ["GET"]
    allow_headers = ["content-type"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "ingest" {
  api_id                 = aws_apigatewayv2_api.captures.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ingest.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 10000
}

resource "aws_apigatewayv2_route" "post_captures" {
  api_id             = aws_apigatewayv2_api.captures.id
  route_key          = "POST /captures"
  target             = "integrations/${aws_apigatewayv2_integration.ingest.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.name_prefix}-captures"
  retention_in_days = 30
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.captures.id
  name        = "$default"
  auto_deploy = true

  # Tope de tráfico para proteger el presupuesto; sobra para una Pi y el simulador.
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }

  # Registro de cada petición (incluidos los fallos controlados de la demo, criterio 4.3).
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      requestTime      = "$context.requestTime"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      caller           = "$context.identity.userArn"
      integrationError = "$context.integrationErrorMessage"
      latencyMs        = "$context.responseLatency"
    })
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.captures.execution_arn}/*/*/captures"
}
