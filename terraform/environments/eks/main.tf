terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

module "eks_cluster" {
  source       = "../../modules/eks"
  cluster_name = "voting-prod-eks"
  aws_region   = "us-east-1"
  vpc_cidr     = "10.0.0.0/16"
  min_nodes    = 3
  max_nodes    = 10
}

output "eks_cluster_endpoint" {
  value = module.eks_cluster.cluster_endpoint
}
