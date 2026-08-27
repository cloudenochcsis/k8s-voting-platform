# AWS VPC & Networking
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name                                        = "${var.cluster_name}-vpc"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }
}

# ponytail: nodes in public subnets (no NAT gateway cost) — fine for a portfolio cluster,
# move nodes to private subnets + NAT before anything real runs here.
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                        = "${var.cluster_name}-public-subnet-${count.index}"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# IAM Role for EKS Cluster
resource "aws_iam_role" "cluster" {
  name = "${var.cluster_name}-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.cluster.name
}

# EKS Cluster
resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  role_arn = aws_iam_role.cluster.arn
  version  = var.kubernetes_version # exact minor pin; EKS will not skip minors on upgrade

  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }

  vpc_config {
    subnet_ids = aws_subnet.public[*].id
  }

  depends_on = [
    aws_iam_role_policy_attachment.cluster_policy
  ]
}

# IAM Role for Node Group
resource "aws_iam_role" "nodes" {
  name = "${var.cluster_name}-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.nodes.name
}

resource "aws_iam_role_policy_attachment" "cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.nodes.name
}

resource "aws_iam_role_policy_attachment" "registry_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.nodes.name
}

# Managed Node Group
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-node-group"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = aws_subnet.public[*].id
  instance_types  = var.node_instance_types
  version         = aws_eks_cluster.main.version # keep nodes on the control-plane minor

  scaling_config {
    desired_size = var.desired_nodes
    max_size     = var.max_nodes
    min_size     = var.min_nodes
  }

  lifecycle {
    ignore_changes = [scaling_config[0].desired_size] # cluster-autoscaler owns this
  }

  depends_on = [
    aws_iam_role_policy_attachment.worker_node_policy,
    aws_iam_role_policy_attachment.cni_policy,
    aws_iam_role_policy_attachment.registry_policy
  ]
}

# ---------------------------------------------------------------------------
# IRSA: OIDC provider + one role per ServiceAccount that needs cloud access.
# This is what makes the eks.amazonaws.com/role-arn annotations in the overlay real.
# ---------------------------------------------------------------------------
data "tls_certificate" "oidc" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc.certificates[0].sha1_fingerprint]
}

# Official policy document for the AWS Load Balancer Controller (pinned to the chart's app version).
data "http" "alb_policy" {
  url                = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.13.0/docs/install/iam_policy.json"
  request_timeout_ms = 10000
}

resource "aws_iam_policy" "alb" {
  name   = "${var.cluster_name}-alb-controller"
  policy = data.http.alb_policy.response_body
}

resource "aws_iam_policy" "external_secrets" {
  name = "${var.cluster_name}-external-secrets"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:voting/*"
    }]
  })
}

locals {
  oidc_host = trimprefix(aws_iam_openid_connect_provider.eks.url, "https://")
  # namespace/serviceaccount -> managed policy (null = identity only, no permissions yet)
  irsa_roles = {
    ebs-csi          = { ns = "kube-system", sa = "ebs-csi-controller-sa", policy = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy" }
    alb-controller   = { ns = "kube-system", sa = "aws-load-balancer-controller", policy = aws_iam_policy.alb.arn }
    external-secrets = { ns = "external-secrets", sa = "external-secrets", policy = aws_iam_policy.external_secrets.arn }
    worker           = { ns = "voting", sa = "sa-worker", policy = null }
    vote             = { ns = "voting", sa = "sa-vote", policy = null }
    eligibility      = { ns = "voting", sa = "sa-eligibility", policy = null }
  }
}

resource "aws_iam_role" "irsa" {
  for_each = local.irsa_roles
  name     = "${var.cluster_name}-${each.key}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.eks.arn }
      Condition = {
        StringEquals = {
          "${local.oidc_host}:sub" = "system:serviceaccount:${each.value.ns}:${each.value.sa}"
          "${local.oidc_host}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "irsa" {
  for_each   = { for k, v in local.irsa_roles : k => v if v.policy != null }
  role       = aws_iam_role.irsa[each.key].name
  policy_arn = each.value.policy
}

# ---------------------------------------------------------------------------
# Managed add-ons. VPC CNI does NOT enforce NetworkPolicy unless told to — without this,
# every NetworkPolicy in k8s/base is silently ignored.
# ---------------------------------------------------------------------------
resource "aws_eks_addon" "vpc_cni" {
  cluster_name                = aws_eks_cluster.main.name
  addon_name                  = "vpc-cni"
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  configuration_values        = jsonencode({ enableNetworkPolicy = "true" })
}

# gp3 volumes (k8s/overlays/eks/storageclass.yaml) need the CSI driver; it is not installed by default.
resource "aws_eks_addon" "ebs_csi" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = aws_iam_role.irsa["ebs-csi"].arn
  depends_on               = [aws_eks_node_group.main]
}
