# Live GCP Infra and Schema Checklist

Source basis: current-thread spec summary, `README.md`, `docs/ARCHITECTURE.md`,
`tasks/subagent-architecture-findings.md`, and `infra/sql/*.sql`.

## Current Repo State

- No Terraform files are present yet.
- Existing SQL assets are reference-only and are not wired into deployment:
  - `infra/sql/bigquery_features.sql`
  - `infra/sql/bigtable_reverse_etl.sql`
  - `infra/sql/alloydb_products.sql`
- The current app intentionally emulates BigQuery, AlloyDB ScaNN, Bigtable, Pub/Sub,
  and Vertex AI locally. A deployable repo needs a separate live-GCP infra layer.

## Required Terraform Resources

- Project/API enablement:
  - `google_project_service` for BigQuery, BigQuery Connection API, Vertex AI,
    Bigtable Admin/Data APIs, AlloyDB, Compute, Service Networking, Pub/Sub,
    Cloud Run, Artifact Registry, IAM, Secret Manager, Cloud Logging/Monitoring.
- Networking:
  - VPC/subnet for private AlloyDB access.
  - Private Service Access via `google_compute_global_address` and
    `google_service_networking_connection`.
  - Serverless VPC Access connector if Cloud Run calls AlloyDB privately.
- BigQuery:
  - `google_bigquery_dataset` in the same regional boundary as Bigtable.
  - `google_bigquery_table` assets for product content, feature registry,
    event/appends source, current item/user features, embeddings, and CQ audit/errors.
  - `google_bigquery_connection` for the Vertex AI remote model.
  - IAM binding for the BigQuery connection service account to call Vertex AI.
  - A deploy step for `CREATE MODEL` and continuous-query `EXPORT DATA` SQL.
- Bigtable:
  - `google_bigtable_instance` with `edition = "ENTERPRISE_PLUS"` if the spec
    explicitly requires Enterprise Plus.
  - At least one SSD cluster with autoscaling; replicated clusters/app profile if
    low-latency multi-zone or regional failover is part of the demo story.
  - `google_bigtable_table` for online features with column family `f`.
  - `google_bigtable_app_profile` for the BigQuery export URI.
  - IAM for the BigQuery continuous-query runner on the Bigtable instance/table.
- AlloyDB:
  - `google_alloydb_cluster`, primary `google_alloydb_instance`, database/user
    bootstrap path, and Secret Manager credentials.
  - Database flags needed by ScaNN preview/advanced modes only if selected.
  - SQL bootstrap for extensions, table DDL, indexes, grants, and seed/load path.
- Pub/Sub and ingestion:
  - `google_pubsub_topic` for retail events and subscription or Dataflow/BigQuery
    ingestion path that lands append-only events in BigQuery.
  - Dead-letter topic/subscription if live events are part of the deployable demo.
- Serving/UI:
  - Artifact Registry repository.
  - Cloud Run service, service account, ingress settings, VPC connector, and IAM.
  - Secret Manager secrets or env-var injection for AlloyDB credentials and endpoint IDs.
- Optional but production-shaped:
  - KMS keys for BigQuery, Bigtable, AlloyDB, Artifact Registry, and Secret Manager.
  - Log-based metrics/alerts for continuous-query lag/failures and stale online features.

## Required Runtime Env Vars

- Core: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_REGION`, `APP_ENV`.
- BigQuery: `BQ_DATASET`, `BQ_LOCATION`, `BQ_CONNECTION_ID`,
  `BQ_EMBEDDING_MODEL`, `BQ_PRODUCT_CONTENT_TABLE`, `BQ_EVENT_TABLE`,
  `BQ_ITEM_FEATURES_TABLE`, `BQ_USER_FEATURES_TABLE`.
- Bigtable: `BIGTABLE_INSTANCE_ID`, `BIGTABLE_APP_PROFILE_ID`,
  `BIGTABLE_FEATURE_TABLE`, `BIGTABLE_COLUMN_FAMILY=f`.
- AlloyDB: `ALLOYDB_CLUSTER`, `ALLOYDB_INSTANCE`, `ALLOYDB_DATABASE`,
  `ALLOYDB_USER`, `ALLOYDB_PASSWORD_SECRET`, `ALLOYDB_HOST` or connector target.
- Vertex AI: `VERTEX_LOCATION`, `VERTEX_RANKER_ENDPOINT`,
  `VERTEX_PRICING_ENDPOINT`, `VERTEX_COUPON_ENDPOINT`.
- Pub/Sub: `EVENT_TOPIC`, optional `EVENT_SUBSCRIPTION`, `DLQ_TOPIC`.
- Ops: `FEATURE_FRESHNESS_SLA_SECONDS`, `LOG_LEVEL`, `TRACE_DEBUG_ENABLED`.

## SQL Assets To Add Or Promote

- BigQuery DDL:
  - Dataset/table DDL for product content, event stream/appends source,
    feature registry, current item/user features, raw embeddings, normalized embeddings,
    continuous-query status/audit, and rejected rows.
  - Remote connection and `CREATE OR REPLACE MODEL` for embeddings.
  - `ML.GENERATE_EMBEDDING` or `AI.GENERATE_EMBEDDING` embedding build SQL.
  - Continuous-query SQL using `APPENDS(...)` in the `FROM` clause and
    `EXPORT DATA OPTIONS(format="CLOUD_BIGTABLE", uri=...)`.
  - Reverse ETL output should include `rowkey` and `_CHANGE_TIMESTAMP`.
- Bigtable schema:
  - Table `online_features` or equivalent with column family `f`.
  - Explicit GC policy/version retention for feature cells.
  - App profile referenced by the BigQuery export URI.
- AlloyDB SQL:
  - `CREATE EXTENSION IF NOT EXISTS alloydb_scann CASCADE;`
  - Product table with `vector(1536)` if embedding dimensionality stays at 1536.
  - ScaNN index DDL, GIN full-text index, and category/price btree index.
  - Query templates for vector-only, text-only, and hybrid retrieval.
  - Seed/load SQL should build the ScaNN index only after enough embeddings exist.

## Syntax And Product Risks To Verify Live

- BigQuery continuous queries:
  - Current `infra/sql/bigtable_reverse_etl.sql` is a one-shot `EXPORT DATA` sketch,
    not a continuous query. A continuous query must use `APPENDS(...)` or supported
    change functions as its source.
  - BigQuery-to-Bigtable exports must target a Bigtable resource in the same regional
    boundary as the BigQuery dataset.
  - Service-account continuous queries have finite run duration; deployment needs
    retry/resume automation and lag monitoring.
- BigQuery to Bigtable export:
  - The URI should include `/appProfiles/APP_PROFILE_ID/tables/TABLE` for explicit
    app-profile routing.
  - Export results require a `rowkey` column of type `STRING` or `BYTES` and at least
    one non-rowkey column.
  - `NULL` exported values can delete existing Bigtable cells; upstream SQL should
    avoid accidental nulls or intentionally coalesce/delete.
  - Add `_CHANGE_TIMESTAMP` if feature freshness relies on Bigtable cell timestamps.
  - Decide `BINARY` vs `TEXT` encoding; `BINARY` changes numeric byte representation.
- BigQuery ML embeddings:
  - `gemini-embedding-001` defaults to 3072 dimensions; the repo SQL requests 1536.
    Keep AlloyDB `vector(1536)` only if this option is accepted in the target region.
  - The input query must expose a `STRING` column named `content`.
  - The remote model, input table, and BigQuery connection must be region-compatible.
  - Consider `AI.GENERATE_EMBEDDING` for new SQL if simplified output names matter.
- AlloyDB ScaNN:
  - `alloydb_scann` must be installed before index creation; it cascades `vector`.
  - ScaNN index creation on empty or very small tables can fail or need deferred/forced
    index creation. Load embeddings before the production index step.
  - `max_num_levels = 2` means a three-level tree in AlloyDB docs; do not label it as
    two-level in docs or tuning notes.
  - Automatically tuned indexes and higher-level ScaNN modes may require database flags;
    avoid preview flags in production unless the spec explicitly accepts pre-GA risk.
- Bigtable Enterprise Plus:
  - Terraform provider support is current, but the deployable repo should pin a
    provider version that supports `edition = "ENTERPRISE_PLUS"`.
  - Confirm the selected region/zone supports the required edition, autoscaling range,
    replication plan, and app-profile routing.

## Official Docs Checked

- BigQuery continuous queries:
  https://docs.cloud.google.com/bigquery/docs/continuous-queries
- BigQuery continuous-query overview and location limits:
  https://docs.cloud.google.com/bigquery/docs/continuous-queries-introduction
- BigQuery export to Bigtable:
  https://docs.cloud.google.com/bigquery/docs/export-to-bigtable
- BigQuery `ML.GENERATE_EMBEDDING`:
  https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/
  bigqueryml-syntax-generate-embedding
- AlloyDB ScaNN:
  https://docs.cloud.google.com/alloydb/docs/ai/create-scann-index
- Terraform Bigtable instance:
  https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/bigtable_instance
