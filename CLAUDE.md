# CLAUDE.md — Student Election Voting Platform

This file gives an LLM (Claude Code or similar) the context needed to help build and deploy this project. It is a Kubernetes skills-refresh project: a student council election voting system supporting ~10,000 concurrent voters, deployed identically to EKS, AKS, and GKE.

## 1. Project Goal

Build a small but architecturally realistic voting platform, then deploy the **same** container images and near-identical manifests to three managed Kubernetes services, adapting only the cloud-specific glue (ingress controller, secrets, storage class, workload identity). The point of the exercise is operational fluency across clouds, not app complexity — keep business logic simple and correct.

Primary skills being refreshed: Deployments/Services/Ingress, ConfigMaps/Secrets, StatefulSets + PVCs, HPA, NetworkPolicies, RBAC, Workload Identity (IRSA / AAD Workload Identity / GKE Workload Identity), GitOps delivery via ArgoCD, Terraform across three providers.

## 2. Core Requirements

- ~10,000 students, each votes exactly once for one candidate slate.
- Students authenticate with a student ID against a source-of-truth eligibility list (mocked as a seeded table/CSV for this project — do not use real student data).
- Ballot secrecy: it must be possible to know *that* a student voted without being able to join that fact to *what* they voted for.
- Results are hidden until an admin/CronJob-triggered "reveal" flips a flag after polls close.
- System must survive a last-hour traffic spike (most real elections spike right before close) — this drives the HPA and queue design, not steady-state load.

## 3. Tech Stack

Kept deliberately narrow so the project stays fast to build and debug — the skills being refreshed are Kubernetes/cloud, not language breadth. One backend language across all services means one Dockerfile pattern, one dependency-scanning setup in CI, and less context-switching while debugging a failing pod at 11pm.

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite, plain CSS or Tailwind | Fast build, static output served by nginx — simplest possible container |
| Backend services (`eligibility-api`, `vote-api`, `results-api`) | Python + FastAPI | Async support (useful under load), fast to scaffold, good typed request/response models via Pydantic — doubles as free input validation |
| Worker | Python, `redis-py` consumer (Streams, consumer group) + `psycopg`/SQLAlchemy for Postgres writes | Same language as the APIs, so shared models/schemas can be reused across services |
| Queue | Redis (Streams, not just a List — gives you consumer groups and at-least-once delivery semantics to talk about in interviews) | Lightweight, in-cluster to start, swappable for managed cache later |
| Database | PostgreSQL 16 | `UNIQUE` constraint on `student_id` is what actually enforces one-vote-per-student — this is the correctness backbone |
| Auth | Short-lived JWT (`PyJWT`), signed with a key pulled from a Secret/Key Vault/Secrets Manager — never hardcoded | Matches the "verify eligibility, issue token, use token" flow described earlier |
| Migrations | Alembic | Standard for FastAPI + SQLAlchemy, also gives you a Job/InitContainer pattern to practice in K8s |
| Reveal-gate | Small Python script, run as a K8s CronJob, flips a `revealed` boolean row or ConfigMap | No separate service needed — a script + CronJob is enough |
| Local dev | `docker-compose.yml` mirroring the five services + Redis + Postgres | Sanity-check before anything touches a real cluster |
| CI | CircleCI (matches your existing GitOps portfolio pipeline) — lint, test, build, push, tag | Reuse patterns you already have muscle memory on |
| GitOps delivery | ArgoCD | Same as your existing setup |
| IaC | Terraform, one module per cloud (`/terraform/modules/eks|aks|gke`) | Matches your HashiCorp certification and existing project structure |
| Load testing | k6 | Scriptable in JS, good for simulating the "last hour" spike described in section 10 |

If you'd rather diversify languages for broader interview talking points (e.g., Go for `worker` to practice a second language + goroutines for consumer concurrency), that's a reasonable swap — flag it in the build session and adjust the Dockerfile/CI steps for that one service accordingly. Default assumption below is Python everywhere unless you say otherwise.

## 4. Service Boundaries

Keep these as separate deployable services even though the project is small — the separation is the point.

| Service | Responsibility | Notes |
|---|---|---|
| `eligibility-api` | Verifies student ID against voter roll, issues short-lived JWT | Separate DB/table from ballots. Never stores vote choice. |
| `vote-api` | Accepts a ballot submission, publishes to queue | Rejects duplicate `student_id` at enqueue time (fast fail) |
| `worker` | Consumes queue, writes ballot to Postgres with a `UNIQUE` constraint on `student_id` | This is the source of truth for "has voted"; handles the real idempotency guarantee |
| `results-api` | Reads aggregated tallies | Checks `reveal` flag before returning real numbers; returns "polls open" otherwise |
| `reveal-gate` (CronJob) | Flips the reveal flag at a scheduled time or on admin trigger | Practice ground for K8s CronJob |
| `frontend` | SPA — login, ballot form, results page | Static build served via nginx or served from an edge/CDN in prod-like setups |

Queue: Redis (Streams or List) is enough at this scale — don't over-engineer with Kafka. The point is practicing the async write pattern, not picking the "correct" enterprise queue.

Database: Postgres. Two logical schemas/tables minimum:
- `voter_roll` (student_id, has_voted boolean, voted_at) — eligibility + turnout tracking, no ballot content
- `ballots` (id, candidate_choice, cast_at) — no student_id column at all, so there is no query path from identity to choice

## 5. Data Model Notes

- `voter_roll.student_id` — unique index, this is what enforces one-vote-per-student
- `ballots` table intentionally has no foreign key back to `voter_roll` — enforce ballot secrecy architecturally, not just by convention
- Consider putting `voter_roll` and `ballots` in separate schemas, or eventually separate databases/namespaces, so a NetworkPolicy can restrict which service can reach which table

## 6. API Contracts (draft — refine during build)

```
POST /eligibility/verify        { student_id }               -> { token }  (eligibility-api)
POST /vote                      { token, candidate_id }        -> { status: queued }  (vote-api)
GET  /results                                                  -> { revealed: bool, tallies?: [...] }  (results-api)
POST /admin/reveal              { admin_token }                -> { revealed: true }  (reveal-gate trigger, or CronJob-only)
```

## 7. Kubernetes Objects to Build (per service, as applicable)

- Deployment (vote-api, results-api, eligibility-api, worker, frontend, redis)
- StatefulSet + PVC (postgres) — or externalize to managed DB on at least one cloud
- Service (ClusterIP internal, LoadBalancer/Ingress for public-facing)
- Ingress — route `/vote`, `/results`, `/eligibility` distinctly
- ConfigMap — non-secret config (reveal time, feature flags)
- Secret — DB creds, JWT signing key (via External Secrets Operator / cloud secret store, not plaintext manifests)
- HPA — on `vote-api` and `worker`, driven by CPU first, queue depth later if time allows
- NetworkPolicy — `ballots` DB access restricted to `worker` and `results-api` only; `voter_roll` DB access restricted to `eligibility-api` and `worker` only
- CronJob — `reveal-gate`
- RBAC — least-privilege ServiceAccounts per service, not one shared default SA

## 8. Repo Structure (suggested)

```
/services
  /eligibility-api
  /vote-api
  /worker
  /results-api
  /frontend
/k8s
  /base                # Kustomize base manifests, cloud-agnostic
  /overlays
    /eks
    /aks
    /gke
/terraform
  /modules
    /eks
    /aks
    /gke
  /environments
    /eks
    /aks
    /gke
/argocd
  /applications         # ArgoCD Application manifests per cluster
/.circleci
  config.yml
```

Use Kustomize overlays (not three divergent manifest trees) so cloud-specific differences stay isolated and reviewable — that's the whole point of the multi-cloud exercise.

## 9. Cloud-Specific Adaptations

| Concern | EKS | AKS | GKE |
|---|---|---|---|
| Ingress controller | AWS Load Balancer Controller | Application Gateway Ingress Controller (AGIC) or nginx-ingress | GKE native Ingress or nginx-ingress |
| Secrets | External Secrets Operator + AWS Secrets Manager | Azure Key Vault CSI driver | Secret Manager + Workload Identity |
| Pod identity for cloud resources | IRSA (IAM Roles for Service Accounts) | Azure AD Workload Identity | GKE Workload Identity |
| Storage class | `gp3` (EBS CSI driver) | Azure Disk CSI | `pd-ssd` |
| Managed DB option | RDS for Postgres | Azure Database for PostgreSQL | Cloud SQL for Postgres |
| Managed cache option | ElastiCache | Azure Cache for Redis | Memorystore |
| Autoscaling | Cluster Autoscaler or Karpenter | Cluster Autoscaler | Cluster Autoscaler or Autopilot |

Suggested build order: **EKS first** (existing Terraform/ArgoCD muscle memory), then **GKE**, then **AKS** — do the DB/cache as in-cluster StatefulSet on EKS, then swap to the managed equivalent on GKE or AKS to force practicing Workload Identity for pod-to-managed-service auth.

## 10. Deployment Flow (per cluster)

1. `terraform apply` — cluster + node pool + networking + IAM/identity setup for that cloud
2. Bootstrap ArgoCD on the cluster (or use a shared ArgoCD instance managing all three as remote clusters)
3. ArgoCD Application points at `/k8s/overlays/<cloud>`
4. CircleCI builds and pushes images on merge to main, tags trigger the overlay's `kustomization.yaml` image tag bump (or use ArgoCD Image Updater)
5. Verify: HPA scaling under `k6` load test, NetworkPolicy denial test (try to hit `ballots` DB from `frontend` pod, confirm it's blocked), CronJob reveal fires on schedule

## 11. Load Testing Plan

Use `k6` or `hey` to simulate the "last hour before polls close" spike:
- Ramp from ~50 RPS to ~2,000 RPS over 5 minutes on `POST /vote`
- Watch `vote-api` and `worker` HPA scale out
- Watch Postgres connections — this is the intended bottleneck; use it as the excuse to add `pgbouncer` or tune `max_connections` / connection pool size in the worker
- Confirm duplicate votes from the same `student_id` are rejected under concurrent load, not just sequential load — this is the real correctness test, not the throughput number

## 12. Explicitly Out of Scope

- Real student PII — use synthetic/seeded student IDs only, never real records
- Production-grade cryptographic ballot secrecy (blind signatures, homomorphic tallying) — architectural separation of identity and ballot is sufficient for this project's goals
- Multi-region / DR — single region per cloud is enough for the skills being practiced here

## 13. Suggested Build Order for the LLM Session

1. Scaffold the five services with minimal working logic and a docker-compose.yml for local sanity check
2. Write Kustomize base manifests against a local kind cluster
3. Add HPA, NetworkPolicy, CronJob, RBAC to the base
4. Write EKS Terraform module + overlay, deploy, verify
5. Write GKE Terraform module + overlay (swap Postgres for Cloud SQL, add Workload Identity), deploy, verify
6. Write AKS Terraform module + overlay (swap Redis for Azure Cache), deploy, verify
7. Wire up CircleCI build/push and ArgoCD sync for all three
8. Run the k6 load test against each cluster, document results for the portfolio writeup

## 14. Notes for the Assisting LLM

- Prioritize correctness of the vote-once guarantee over feature breadth — this is the load-bearing design decision of the whole project.
- When generating manifests, always explain *why* a cloud-specific field differs (e.g., why the storage class name differs) rather than just outputting it — the goal is understanding, not copy-paste.
- Default to Kustomize over raw per-cloud manifest duplication unless there's a good reason.
- Flag any point where a "shortcut" would defeat the purpose of the exercise (e.g., using `latest` tags, disabling NetworkPolicies to make debugging easier and forgetting to re-enable them).
