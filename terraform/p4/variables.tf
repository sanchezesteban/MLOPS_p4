variable "region" {
  description = "Región de todos los recursos de P4."
  type        = string
  default     = "us-east-2"
}

variable "name_prefix" {
  description = "Prefijo de nombres de recursos."
  type        = string
  default     = "mlops-p4"
}

variable "team_members" {
  description = "Integrantes con usuario IAM de mínimo privilegio (sin consola; las llaves se generan fuera de Terraform)."
  type        = set(string)
  default     = ["uriel", "juanpablo", "esteban"]
}

variable "device_id" {
  description = "Identidad del dispositivo edge (contrato del evento v1)."
  type        = string
  default     = "rpi-zero2w-01"
}

variable "budget_limit_usd" {
  description = "Límite mensual de la alerta de presupuesto, en USD."
  type        = number
  default     = 10
}

variable "budget_emails" {
  description = "Correos que reciben la alerta de presupuesto. Se define en terraform.tfvars (ignorado por Git)."
  type        = list(string)

  validation {
    condition     = length(var.budget_emails) > 0
    error_message = "Define al menos un correo en budget_emails."
  }
}

variable "evaluator_access_until" {
  description = "Fecha (UTC, ISO-8601) en que expira el acceso de solo lectura del evaluador."
  type        = string
  default     = "2026-11-17T23:59:59Z"
}

variable "portal_origins" {
  description = "Orígenes del portal que pueden consultar GET /captures desde el navegador (CORS)."
  type        = list(string)
  default     = ["http://localhost:8080", "http://localhost:5173"]
}

variable "portal_instance_type" {
  description = "Tipo de la EC2 del portal."
  type        = string
  default     = "t3.small"
}

variable "portal_repo_url" {
  description = "Repositorio público que clona la EC2 del portal."
  type        = string
  default     = "https://github.com/sanchezesteban/MLOPS_p4.git"
}

variable "portal_git_ref" {
  description = "Rama que despliega la EC2 al arrancar (luego: scripts/p4_portal_deploy.sh <rama>)."
  type        = string
  default     = "main"
}

variable "portal_allowed_cidrs" {
  description = "Redes que pueden abrir el portal por HTTP (por defecto, cualquiera: el evaluador entra desde fuera)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
