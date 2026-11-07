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

resource "aws_vpc_security_group_ingress_rule" "ssh_from_operator" {
  security_group_id = aws_security_group.linkr_staging.id
  description       = "SSH from the operator IP only"
  cidr_ipv4         = var.operator_ip_cidr
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_egress_rule" "all_outbound" {
  security_group_id = aws_security_group.linkr_staging.id
  description       = "Allow all outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
