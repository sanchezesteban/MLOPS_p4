output "region" {
  value = var.region
}

output "models_bucket" {
  description = "Remote DVC de modelos y dataset (#7)."
  value       = aws_s3_bucket.this["models"].id
}

output "captures_bucket" {
  description = "Fotografías de las capturas edge (#16)."
  value       = aws_s3_bucket.this["captures"].id
}

output "captures_table" {
  description = "Metadatos de las capturas; llave capture_id, índice by_captured_at."
  value       = aws_dynamodb_table.captures.name
}

output "team_users" {
  value = [for user in aws_iam_user.team : user.name]
}

output "device_user" {
  value = aws_iam_user.device.name
}
