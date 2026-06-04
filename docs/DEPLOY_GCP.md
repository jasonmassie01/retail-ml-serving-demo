# Deploy To GCP

This repo is ready to publish to GitHub and use as a GCP live-demo source. It does
not create resources until you run the scripts below.

## Prerequisites

- Billing-enabled GCP project.
- `gcloud`, `bq`, Docker, Terraform, Node.js, and Python.
- Application-default or user credentials with permission to create the listed services.
- Vertex AI endpoint IDs for ranking, pricing, and coupon propensity, or placeholder
  endpoints to swap later.

Run:

```powershell
.\scripts\check-prereqs.ps1 -ProjectId YOUR_PROJECT
```

## Provision And Deploy

```powershell
$env:TF_VAR_alloydb_password = "REPLACE_WITH_STRONG_PASSWORD"
.\scripts\deploy-gcp.ps1 `
  -ProjectId YOUR_PROJECT `
  -Region us-central1 `
  -Zone us-central1-b `
  -BqLocation US `
  -VertexRankingEndpoint "projects/YOUR_PROJECT/locations/us-central1/endpoints/..." `
  -VertexPricingEndpoint "projects/YOUR_PROJECT/locations/us-central1/endpoints/..." `
  -VertexCouponEndpoint "projects/YOUR_PROJECT/locations/us-central1/endpoints/..."
```

The script applies Terraform once with a placeholder Cloud Run image, builds and
pushes the FastAPI image to Artifact Registry, reapplies Cloud Run with the real
image, runs the batch SQL templates, and executes the AlloyDB loader job.

The batch SQL and loader sequence does the full serving data load:

1. Copies the public `bigquery-public-data.thelook_ecommerce` tables into your
   `retail_demo` dataset.
2. Builds deterministic product content plus Gemini embedding tables in BigQuery.
3. Computes item/user feature tables from the copied theLook data.
4. Exports current item features from BigQuery to Bigtable with row keys like
   `item#123`.
5. Runs `retail-alloydb-loader` as a Cloud Run Job on the VPC connector so it can
   reach the private AlloyDB instance and upsert product content plus embeddings.

Use `-SkipSql` to skip the BigQuery/Bigtable SQL batch and `-SkipAlloyDbLoad` to
skip the AlloyDB loader job.

To rerun only the AlloyDB load after changing embeddings or catalog content:

```powershell
.\scripts\run-alloydb-load.ps1 -ProjectId YOUR_PROJECT -Region us-central1
```

## Continuous Query Upgrade

BigQuery continuous queries require an Enterprise or Enterprise Plus reservation with
a `CONTINUOUS` assignment. After that reservation exists, start the dynamic feature
query:

```powershell
.\scripts\run-sql.ps1 `
  -ProjectId YOUR_PROJECT `
  -StartContinuousQuery `
  -ContinuousQueryServiceAccount "retail-feature-pipeline@YOUR_PROJECT.iam.gserviceaccount.com"
```

## Local API And Web

```powershell
.\scripts\run-api-local.ps1 -Mode emulator -Port 8080
$env:VITE_API_BASE_URL = "http://127.0.0.1:8080"
npm run dev
```

## Teardown

Stateful resources default to deletion protection. To destroy a disposable demo, set
`deletion_protection=false` in Terraform variables, apply that change, then destroy.
Keep the generated `terraform.tfstate` secure because it contains sensitive state.
