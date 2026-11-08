terraform {
  required_version = "~> 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      owner   = "alfred"
      project = "linkr"
      stage   = "staging"
    }
  }
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "linkr_staging" {
  name        = "linkr-staging"
  description = "Linkr staging: inbound locked to the operator IP"
  vpc_id      = data.aws_vpc.default.id
}

variable "operator_ip_cidr" {
  type        = string
  description = "Alfred's public IP in CIDR form, e.g. 1.2.3.4/32. Never committed."
}

resource "aws_vpc_security_group_ingress_rule" "api_from_operator" {
  security_group_id = aws_security_group.linkr_staging.id
  description       = "Linkr API from the operator IP only"
  cidr_ipv4         = var.operator_ip_cidr
  ip_protocol       = "tcp"
  from_port         = 8000
  to_port           = 8000
}


resource "aws_vpc_security_group_egress_rule" "all_outbound" {
  security_group_id = aws_security_group.linkr_staging.id
  description       = "Allow all outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_iam_role" "linkr_staging" {
  name        = "linkr-staging-ec2"
  description = "Identity worn by the Linkr staging instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.linkr_staging.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "linkr_staging" {
  name = "linkr-staging-ec2"
  role = aws_iam_role.linkr_staging.name
}

resource "aws_instance" "linkr_staging" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  vpc_security_group_ids      = [aws_security_group.linkr_staging.id]
  iam_instance_profile        = aws_iam_instance_profile.linkr_staging.name
  associate_public_ip_address = true

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "linkr-staging"
  }
}

output "staging_public_ip" {
  description = "Public IP of the staging instance"
  value       = aws_instance.linkr_staging.public_ip
}
