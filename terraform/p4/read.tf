# API de lectura para el portal (#17): GET /captures → Lambda de solo lectura.
# Sin firma, para que el navegador del portal la consulte; CORS limitado a
# `portal_origins` y tope de tráfico propio. Solo expone lo que el portal ya muestra.

data "archive_file" "read" {
  type        = "zip"
  source_file = "${path.module}/../../app/edge_ingest/read_api.py"
  output_path = "${path.module}/build/read.zip"
}

resource "aws_iam_role" "read" {
  name = "${var.name_prefix}-read-lambda"
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

data "aws_iam_policy_document" "read" {
  statement {
    sid       = "QueryNewestFirst"
    actions   = ["dynamodb:Query"]
    resources = ["${aws_dynamodb_table.captures.arn}/index/by_captured_at"]
  }

  # Necesario para firmar las URL de las fotografías; no permite escribir.
  statement {
    sid       = "SignImageUrls"
    actions   = ["s3:GetObject"]
    resources = ["${local.captures_arn}/captures/*"]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.read.arn}:*"]
  }
}

resource "aws_iam_role_policy" "read" {
  name   = "${var.name_prefix}-read"
  role   = aws_iam_role.read.id
  policy = data.aws_iam_policy_document.read.json
}

resource "aws_cloudwatch_log_group" "read" {
  name              = "/aws/lambda/${var.name_prefix}-read"
  retention_in_days = 30
}

resource "aws_lambda_function" "read" {
  function_name    = "${var.name_prefix}-read"
  role             = aws_iam_role.read.arn
  runtime          = "python3.12"
  handler          = "read_api.lambda_handler"
  filename         = data.archive_file.read.output_path
  source_code_hash = data.archive_file.read.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      CAPTURES_BUCKET = aws_s3_bucket.this["captures"].id
      CAPTURES_TABLE  = aws_dynamodb_table.captures.name
    }
  }

  depends_on = [aws_iam_role_policy.read, aws_cloudwatch_log_group.read]
}

resource "aws_apigatewayv2_integration" "read" {
  api_id                 = aws_apigatewayv2_api.captures.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.read.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 10000
}

resource "aws_apigatewayv2_route" "get_captures" {
  api_id             = aws_apigatewayv2_api.captures.id
  route_key          = "GET /captures"
  target             = "integrations/${aws_apigatewayv2_integration.read.id}"
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "read_api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.read.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.captures.execution_arn}/*/GET/captures"
}
