# Architecture

The source specification locks a Google Cloud architecture. This repo implements both
a local emulator and deployable live service code for the same contracts.

## Cloud-To-Local Mapping

| Spec layer | Cloud service | Repo implementation |
| --- | --- | --- |
| Offline feature store | BigQuery | SQL templates, Terraform dataset, API trace |
| Catalog and vectors | AlloyDB + ScaNN | Loader job plus live `AlloyDbCatalog` adapter |
| Online feature store | Bigtable | Terraform table plus live `BigtableFeatureStore` |
| Event stream | Pub/Sub -> BigQuery -> Bigtable | Pub/Sub API publish plus SQL CQ upgrade |
| Model serving | Vertex AI Endpoints | live endpoint scorer plus emulator scorer |
| Observability | query profile and freshness checks | trace rail, debug SQL, freshness panel |

## Unified Serving Flow

Every use case runs the same stages:

1. BigQuery-stage feature definitions are already materialized as local fixtures.
2. AlloyDB ScaNN-stage retrieval returns candidates or a direct pricing product.
3. Bigtable-stage reads fetch `user#...` and `item#...` feature rows.
4. Vertex AI-stage scoring ranks products or produces a bounded price/coupon decision.

The local pipeline is implemented in `src/domain/servingEngine.ts`. The deployable
API pipeline is implemented in `services/api/app/serving.py`.

## Correctness Properties

- Hybrid retrieval blends vector similarity and text rank before final limiting.
- Pricing never returns a price below `cost * 1.18`.
- Feature freshness is based on Bigtable-style cell timestamps.
- Live events update feature values, timestamps, freshness, and downstream decisions.
- Point-in-time training examples read feature history at or before the label event.

## Deployable Surfaces

- `infra/terraform/` provisions BigQuery, Bigtable, AlloyDB, Pub/Sub, Artifact
  Registry, Cloud Run, IAM, networking, and secrets.
- `infra/sql/` materializes theLook working copies, product content, embeddings,
  features, AlloyDB schema, Bigtable reverse ETL, continuous-query examples, and
  point-in-time training examples.
- `services/api/app/alloydb_loader.py` runs as the `retail-alloydb-loader` Cloud
  Run Job and copies enriched BigQuery product content plus embeddings into
  AlloyDB over the private VPC path.
- `services/api/` is the Cloud Run service. `SERVING_MODE=live` enables real Google
  Cloud clients; `SERVING_MODE=emulator` keeps CI and local demos credential-free.
- `src/services/servingClient.ts` sends the React app to the live API when
  `VITE_API_BASE_URL` is set, otherwise it uses the local emulator.
