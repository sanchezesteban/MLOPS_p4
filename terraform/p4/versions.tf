terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # Estado remoto en el bucket de state ya existente de la cuenta (versionado).
  # Key propia para P4; `use_lockfile` usa el bloqueo nativo de S3 (Terraform >= 1.10).
  backend "s3" {
    bucket       = "proyecto2-prod-tfstate-595981034933"
    key          = "p4/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "mlops-p4"
      ManagedBy = "terraform"
      Issue     = "P4-04"
    }
  }
}
