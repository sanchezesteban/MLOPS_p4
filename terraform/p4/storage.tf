data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  buckets = {
    # Remote DVC: best.pt, ONNX FP32/INT8 y dataset (#7).
    models = "${var.name_prefix}-models-${local.account_id}"
    # Fotografías de las capturas edge (#16).
    captures = "${var.name_prefix}-captures-${local.account_id}"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_policy" "https_only" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [each.value.arn, "${each.value.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.this]
}

# Metadatos de las capturas. Llave `capture_id`: la ingesta (#16) escribe con
# `attribute_not_exists(capture_id)` para que un reintento no duplique.
# El índice `by_captured_at` permite listar de la más reciente a la más antigua (#17):
# `gsi_pk` es una constante ("capture") y `captured_at_utc` el ISO-8601 normalizado a UTC
# (`captured_at` conserva la zona horaria original y no ordena bien como texto).
resource "aws_dynamodb_table" "captures" {
  name         = "${var.name_prefix}-captures"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "capture_id"

  attribute {
    name = "capture_id"
    type = "S"
  }

  attribute {
    name = "gsi_pk"
    type = "S"
  }

  attribute {
    name = "captured_at_utc"
    type = "S"
  }

  global_secondary_index {
    name            = "by_captured_at"
    projection_type = "ALL"

    key_schema {
      attribute_name = "gsi_pk"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "captured_at_utc"
      key_type       = "RANGE"
    }
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  deletion_protection_enabled = true
}
