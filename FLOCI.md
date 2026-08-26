# Local Multi-Cloud Emulation with Floci & Floci UI

This project integrates [Floci](https://floci.io/) — an ultra-fast, MIT-licensed, zero-credential local cloud emulator — along with **Floci UI** (a browser-based cloud console) to emulate AWS, GCP, and Azure services locally with zero cloud costs and instant startup (~24 ms).

---

## 1. Quick Start

### Start the full stack (Voting App + Floci Multi-Cloud + Floci UI)
```bash
make floci-up
# or: docker compose -f docker-compose.floci.yml up -d
```

### Access UIs in Browser:
- **Voting Platform SPA**: [http://localhost:8080](http://localhost:8080)
- **Floci Multi-Cloud Console**: [http://localhost:4500](http://localhost:4500)

### Seed sample cloud resources:
```bash
make floci-init
```

---

## 2. Emulated Cloud Endpoints

| Cloud / Service | Local Endpoint | Key Emulated Services |
|---|---|---|
| **Floci UI Console** | `http://localhost:4500` | Multi-cloud visual dashboard |
| **AWS (Floci Core)** | `http://localhost:4566` | S3, Secrets Manager, SQS, DynamoDB, RDS, ElastiCache |
| **GCP (Floci GCP)** | `http://localhost:4588` | Google Cloud Storage, Secret Manager, Cloud SQL |
| **Azure (Floci Azure)** | `http://localhost:4577` | Blob Storage, Key Vault, Azure Queues |

---

## 3. Interacting via CLIs

### AWS CLI
```bash
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

# Create an S3 bucket
aws s3 mb s3://student-voting-audit-logs

# Store a secret in Secrets Manager
aws secretsmanager create-secret \
  --name "voting/jwt-secret" \
  --secret-string '{"JWT_SECRET":"voting-super-secret-jwt-key"}'
```

### Google Cloud CLI (`gcloud`)
```bash
export CLOUDSDK_API_ENDPOINT_OVERRIDES_STORAGE=http://localhost:4588/
export CLOUDSDK_CORE_PROJECT=floci-local

# Create a GCS bucket
gcloud storage buckets create gs://student-voting-backup
```

### Azure CLI (`az`)
```bash
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://localhost:4577/devstoreaccount1;"

# Create a blob container
az storage container create -n election-artifacts
```

---

## 4. Running Terraform Locally Against Floci

To dry-run Terraform modules against Floci without touching real cloud accounts, override the provider endpoints:

```hcl
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3             = "http://localhost:4566"
    secretsmanager = "http://localhost:4566"
    sqs            = "http://localhost:4566"
    iam            = "http://localhost:4566"
  }
}
```
