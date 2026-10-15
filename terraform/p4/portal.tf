# Portal de P1–P3 desplegado en AWS (#18, rúbrica 5.1 y M3): una EC2 con docker compose.
# Solo el portal base (frontend, backend, MariaDB, MinIO y Copilot); el entrenamiento del
# P3 (trainer-worker, ml-api, mlflow) no se levanta porque requiere PyTorch y no lo evalúa
# el P4. Puerto 80 abierto; sin SSH (administración por SSM Session Manager).

locals {
  portal_services = ["mariadb", "minio", "backend", "copilot", "frontend"]

  portal_compose_override = yamlencode({
    services = merge(
      { for service in local.portal_services : service => { restart = "unless-stopped" } },
      {
        # `minio/minio` (Docker Hub) y `quay.io/minio/minio` ya no se pueden descargar;
        # la imagen de Chainguard acepta el mismo comando y variables. Corre como root
        # para poder escribir en el volumen `minio_data`.
        minio = {
          restart = "unless-stopped"
          image   = "cgr.dev/chainguard/minio:latest"
          user    = "0:0"
        }
        frontend = {
          restart = "unless-stopped"
          ports   = ["80:80"]
          build = {
            args = {
              VITE_API_BASE_URL     = "/api"
              VITE_CAPTURES_API_URL = aws_apigatewayv2_api.captures.api_endpoint
            }
          }
        }
      },
    )
  })
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "portal" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = "${var.region}a"
  default_for_az    = true
}

data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

resource "aws_security_group" "portal" {
  name        = "${var.name_prefix}-portal"
  description = "Portal P1-P4: solo HTTP de entrada"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "portal_http" {
  for_each = toset(var.portal_allowed_cidrs)

  security_group_id = aws_security_group.portal.id
  description       = "HTTP del portal"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_egress_rule" "portal_all" {
  security_group_id = aws_security_group.portal.id
  description       = "Salida para paquetes, imagenes de Docker, GitHub y SSM"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_iam_role" "portal" {
  name = "${var.name_prefix}-portal-ec2"
  path = "/${var.name_prefix}/"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "portal_ssm" {
  role       = aws_iam_role.portal.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "portal" {
  name = "${var.name_prefix}-portal-ec2"
  role = aws_iam_role.portal.name
}

resource "aws_instance" "portal" {
  ami                    = data.aws_ssm_parameter.ubuntu.value
  instance_type          = var.portal_instance_type
  subnet_id              = data.aws_subnet.portal.id
  vpc_security_group_ids = [aws_security_group.portal.id]
  iam_instance_profile   = aws_iam_instance_profile.portal.name

  user_data = templatefile("${path.module}/portal_user_data.sh.tftpl", {
    repo_url         = var.portal_repo_url
    git_ref          = var.portal_git_ref
    services         = join(" ", local.portal_services)
    compose_override = local.portal_compose_override
  })
  user_data_replace_on_change = false

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${var.name_prefix}-portal" }

  lifecycle {
    # Una AMI nueva de Ubuntu no debe reemplazar la instancia ya desplegada.
    ignore_changes = [ami, user_data]
  }
}

# IP fija: la URL del portal y el origen CORS no cambian al apagar y prender la instancia.
# Se crea aparte de la asociación para evitar un ciclo: el CORS de la API usa esta IP y
# la instancia usa la URL de la API.
resource "aws_eip" "portal" {
  domain = "vpc"
  tags   = { Name = "${var.name_prefix}-portal" }
}

resource "aws_eip_association" "portal" {
  allocation_id = aws_eip.portal.id
  instance_id   = aws_instance.portal.id
}
