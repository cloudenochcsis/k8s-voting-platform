terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }
  # ponytail: local state. Add an S3 backend before a second person or CI touches this.
}

provider "aws" {
  region = "us-east-1"
}

module "eks_cluster" {
  source             = "../../modules/eks"
  cluster_name       = "voting-prod-eks"
  kubernetes_version = "1.35"
  aws_region         = "us-east-1"
  vpc_cidr           = "10.0.0.0/16"
  min_nodes          = 3
  max_nodes          = 10
}

output "eks_cluster_endpoint" {
  value = module.eks_cluster.cluster_endpoint
}

output "irsa_role_arns" {
  value = module.eks_cluster.irsa_role_arns
}
