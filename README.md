# Kubernetes Multi-Cloud Student Election Voting Platform

A high-concurrency, multi-cloud student council election voting platform architected to support 10,000+ concurrent voters. Built to demonstrate containerized microservices deployment across three major cloud providers (Amazon EKS, Google Cloud GKE, and Microsoft Azure AKS) using a single codebase, Kustomize overlays, GitOps delivery via ArgoCD, and infrastructure as code via Terraform.

---

## 1. Architecture Overview

The system is partitioned into decoupled microservices communicating asynchronously via Redis Streams and persisting data into PostgreSQL.

```
                                  +-----------------------+
                                  |    Frontend (SPA)     |
                                  +-----------+-----------+
                                              |
                                  +-----------v-----------+
                                  |   Ingress Controller  |
                                  +-----+-----------+-----+
                                        |           |
                      +-----------------+           +-----------------+
                      |                                               |
            +---------v---------+                           +---------v---------+
            |  eligibility-api  |                           |     vote-api      |
            |   (Verify & JWT)  |                           | (Fast-Fail Check) |
            +---------+---------+                           +---------+---------+
                      |                                               |
                      | Reads voter_roll                              | Enqueues payload
                      v                                               v
            +-------------------+                           +-------------------+
            |  voter_roll Table |                           |   Redis Streams   |
            | (Turnout Tracker) |                           |   (vote_stream)   |
            +-------------------+                           +---------+---------+
                      ^                                               |
                      | Updates has_voted = TRUE                      | xreadgroup
                      |                                               v
                      |                                     +-------------------+
                      |                                     |    worker Pods    |
                      |                                     | (Single Vote Tx)  |
                      |                                     +---------+---------+
                      |                                               |
                      +-----------------------+-----------------------+
                                              |
                                              | Writes anonymous vote
                                              v
                                    +-------------------+
                                    |   ballots Table   |
                                    | (Ballot Secrecy)  |
                                    +---------^---------+
                                              |
                                              | Queries tallies
                                    +---------+---------+
                                    |    results-api    |
                                    |   & Reveal Gate   |
                                    +-------------------+
```

### Core Design Guarantees

1. **Strict Vote-Once Enforcement**:
   - **Fast-Fail Layer**: `vote-api` acquires a distributed lock in Redis via `SETNX` with a key TTL of 86400 seconds. Duplicate vote attempts are rejected immediately at the API edge with HTTP 409 Conflict.
   - **Database Consistency Layer**: The `worker` executes an atomic SQL transaction:
     ```sql
     UPDATE voter_roll SET has_voted = TRUE, voted_at = NOW()
     WHERE student_id = %s AND has_voted = FALSE;
     ```
     Only if the update affects exactly 1 row does the worker proceed to insert the ballot into the `ballots` table and acknowledge the message in Redis (`XACK`).

2. **Architectural Ballot Secrecy**:
   - The `voter_roll` table tracks student identity and turnout state (`student_id`, `has_voted`, `voted_at`).
   - The `ballots` table stores only candidate selections and timestamps (`id`, `candidate_choice`, `cast_at`).
   - There are zero foreign keys, IDs, or references connecting `ballots` back to `voter_roll`.

3. **Results Confidentiality**:
   - `results-api` evaluates the `election_state.revealed` boolean flag before serving tally computations.
   - While polls remain open, queries to `/results` return `{"revealed": false}`.
   - A scheduled Kubernetes CronJob (`reveal-gate`) or an authenticated admin call flips the reveal state flag once polls officially close.

---

## 2. Tech Stack

| Layer | Technology | Details |
|---|---|---|
| Frontend | React / Vanilla JS + Nginx | Static single page application served via lightweight Nginx container |
| APIs | Python 3.11 + FastAPI + Pydantic v2 | High-throughput asynchronous REST APIs |
| Queue / Cache | Redis 7 | Redis Streams with Consumer Groups (`xreadgroup`) and atomic locks (`SETNX`) |
| Database | PostgreSQL 16 | ACID-compliant relational storage with separate identity and ballot tables |
| Containerization | Docker & Multi-stage builds | Minimal container images running unprivileged processes |
| Kubernetes | K8s 1.30+ / Kustomize | Base manifests with overlays for EKS, GKE, and AKS |
| Infrastructure as Code | Terraform (HashiCorp) | Modular IaC for AWS, GCP, and Azure environments |
| GitOps | ArgoCD | Declarative application definitions targeting cloud overlays |
| CI/CD | CircleCI | Automated linting, logic testing, and container build/push pipelines |
| Local Cloud Emulation | Floci & Floci UI | Offline emulation for AWS, GCP, and Azure cloud services |
| Load Testing | k6 | Distributed JS-scripted load testing simulating election closing traffic spikes |

---

## 3. Repository Structure

```
.
|-- .circleci/
|   `-- config.yml                     # CircleCI CI/CD pipeline definition
|-- argocd/
|   `-- applications/
|       `-- voting-apps.yaml           # ArgoCD Application manifests for EKS, GKE, and AKS
|-- db/
|   `-- init.sql                       # Database schema and 10,000 synthetic voter seed
|-- k8s/
|   |-- base/                          # Cloud-agnostic Kustomize base manifests
|   |   |-- deployments/               # Deployments for all microservices
|   |   |-- statefulsets/              # PostgreSQL StatefulSet and PVC definition
|   |   |-- configmap.yaml             # Shared application configurations
|   |   |-- secrets.yaml               # Database credentials and JWT secrets
|   |   |-- ingress.yaml               # Routing configuration across API paths
|   |   |-- hpa.yaml                   # HorizontalPodAutoscalers for vote-api and worker
|   |   |-- network-policies.yaml      # Zero-trust namespace network isolation policies
|   |   |-- rbac.yaml                  # Least-privilege ServiceAccounts
|   |   |-- cronjob-reveal.yaml        # Scheduled results reveal CronJob
|   |   `-- kustomization.yaml         # Base Kustomize bundle
|   `-- overlays/                      # Cloud provider overlays
|       |-- eks/                       # AWS EKS overlay (ALB Ingress, gp3, IRSA)
|       |-- gke/                       # GCP GKE overlay (GCE Ingress, premium-rwo, WI)
|       `-- aks/                       # Azure AKS overlay (AGIC Ingress, managed-csi, Entra WI)
|-- load-test/
|   `-- spike.js                       # k6 load testing script (50 to 2,000 RPS)
|-- scripts/
|   `-- init_floci.py                  # Local cloud resource seeder for Floci
|-- services/
|   |-- eligibility-api/               # Verification & JWT token issuance service
|   |-- vote-api/                      # Fast-fail duplicate checking & enqueue service
|   |-- worker/                        # Stream consumer & transactional database worker
|   |-- results-api/                   # Aggregated tallies & turnout reporting service
|   |-- reveal-gate/                   # Polls-close reveal trigger script
|   `-- frontend/                      # Web UI for voter interaction
|-- terraform/
|   |-- environments/                  # Root environments (eks, gke, aks)
|   `-- modules/                       # Reusable infrastructure modules (eks, gke, aks)
|-- docker-compose.yml                 # Local development stack
|-- docker-compose.floci.yml           # Local multi-cloud emulation stack with Floci UI
|-- Makefile                           # Developer automation targets
|-- test_e2e.py                        # Standalone end-to-end Python test suite
`-- FLOCI.md                           # Documentation for local cloud emulation
```

---

## 4. Microservices Breakdown

### 1. `eligibility-api` (Port 8001)
- **Path**: `POST /eligibility/verify`
- **Payload**: `{"student_id": "STU00042"}`
- **Behavior**: Validates student ID against `voter_roll`. If valid and `has_voted == FALSE`, generates and returns a signed 15-minute JWT (`HS256`).

### 2. `vote-api` (Port 8002)
- **Path**: `POST /vote`
- **Payload**: `{"token": "<jwt>", "candidate_id": "Slate 1"}`
- **Behavior**: Verifies JWT cryptographic signature. Acquires an atomic lock in Redis via `SETNX` on key `voted_lock:<student_id>`. Enqueues the vote payload to Redis Stream `vote_stream`.

### 3. `worker`
- **Behavior**: Runs as a daemon in consumer group `vote_workers`. Reads batches of messages using `XREADGROUP`, executes the atomic transactional single-vote update on PostgreSQL, inserts the choice into `ballots`, and commits the transaction before sending `XACK`.

### 4. `results-api` (Port 8003)
- **Path**: `GET /results`
- **Behavior**: Checks `election_state.revealed`. If false, returns hidden status. If true, computes candidate tallies, total turnout, and turnout percentages.
- **Path**: `POST /admin/reveal` (Header: `X-Admin-Secret`)
- **Behavior**: Allows administrators to reveal results prior to scheduled CronJob execution.

### 5. `frontend` (Port 80 / 8080)
- **Behavior**: Responsive browser interface with tabs for voter eligibility check, ballot submission, real-time results graphing, and admin control.

---

## 5. Multi-Cloud Kubernetes Adaptations

Kustomize overlays isolate cloud-specific infrastructure requirements while keeping container code 100% portable:

| Configuration Area | Amazon EKS Overlay (`/k8s/overlays/eks`) | Google Cloud GKE Overlay (`/k8s/overlays/gke`) | Microsoft Azure AKS Overlay (`/k8s/overlays/aks`) |
|---|---|---|---|
| Ingress Class | `spec.ingressClassName: alb` | `spec.ingressClassName: gce` | `spec.ingressClassName: azure-application-gateway` |
| Storage Class | `gp3` (EBS CSI Driver) | `premium-rwo` (GCE Persistent Disk) | `managed-csi` (Azure Disk CSI) |
| Workload Identity | IAM Roles for Service Accounts (`eks.amazonaws.com/role-arn`) | GKE Workload Identity (`iam.gke.io/gcp-service-account`) | Microsoft Entra Workload ID (`azure.workload.identity/client-id` + labels) |
| Container Registry | AWS ECR (`*.dkr.ecr.*.amazonaws.com`) | Google Artifact Registry (`*-docker.pkg.dev`) | Azure Container Registry (`*.azurecr.io`) |

---

## 6. Infrastructure as Code (Terraform)

Terraform modules provision the full networking and Kubernetes control plane on each cloud provider.

### Provisioning Amazon EKS
```bash
cd terraform/environments/eks
terraform init
terraform plan
terraform apply
```

### Provisioning Google Cloud GKE
```bash
cd terraform/environments/gke
terraform init
terraform plan
terraform apply
```

### Provisioning Microsoft Azure AKS
```bash
cd terraform/environments/aks
terraform init
terraform plan
terraform apply
```

---

## 7. Local Development & Testing

### Option A: Standard Local Development
Start the application services, PostgreSQL, and Redis:
```bash
make dev
# or: docker compose up -d
```
Access the application frontend at `http://localhost:8080`.

### Option B: Local Multi-Cloud Emulation with Floci & Floci UI
Start the application alongside Floci emulating AWS, GCP, and Azure cloud services:
```bash
make floci-up
# or: docker compose -f docker-compose.floci.yml up -d
```

Seed sample cloud resources (S3 audit buckets, Secrets Manager secrets):
```bash
make floci-init
```

Access browser dashboards:
- **Voting Application Web UI**: `http://localhost:8080`
- **Floci Multi-Cloud Console**: `http://localhost:4500`
- **Floci AWS Core Endpoint**: `http://localhost:4566`
- **Floci GCP Endpoint**: `http://localhost:4588`
- **Floci Azure Endpoint**: `http://localhost:4577`

---

## 8. Automated Testing & Load Testing

### Run Logic & Security Verification Tests
A self-contained Python test suite validates JWT issuance, single-vote transactional guarantees, ballot secrecy decoupling, and results gating:
```bash
make test
# or: python3 test_e2e.py
```

### Run k6 Load Test (Simulating Peak Election Spike)
Simulates a surge of concurrent voters ramping from 50 to 2,000 RPS on `POST /vote`:
```bash
make k6-load
# or: k6 run load-test/spike.js
```

---

## 9. GitOps Delivery with ArgoCD

ArgoCD manages multi-cluster delivery by tracking the repository and synchronizing overlay changes automatically:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: student-voting-eks
  namespace: argocd
spec:
  project: default
  source:
    repoURL: 'https://github.com/cloudenochcsis/k8s-voting-platform.git'
    targetRevision: HEAD
    path: k8s/overlays/eks
  destination:
    server: 'https://kubernetes.default.svc'
    namespace: voting
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

---

## 10. CI/CD with CircleCI

The automated CircleCI pipeline defined in `.circleci/config.yml` triggers on merge to `main`:
1. **Test Job**: Runs `test_e2e.py` inside a Python 3.11 executor to verify application logic and ballot secrecy before building images.
2. **Build & Push Job**: Uses remote Docker execution to build all 6 container images (`eligibility-api`, `vote-api`, `worker`, `results-api`, `reveal-gate`, and `frontend`) tagged with the commit SHA (`${CIRCLE_SHA1}`).
