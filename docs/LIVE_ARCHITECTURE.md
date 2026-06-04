# Live Architecture

The repo now has two execution modes:

- `emulator`: React and FastAPI run with deterministic in-repo data.
- `live`: FastAPI calls Google Cloud services provisioned by Terraform.

## Service Flow

```mermaid
flowchart LR
  UI["React demo"] --> API["Cloud Run FastAPI"]
  Look["theLook public BQ dataset"] --> BQSeed["BQ copy + enrichment SQL"]
  BQSeed --> BQ
  BQSeed --> Loader["Cloud Run AlloyDB loader job"]
  Loader --> Alloy
  BQSeed --> BTExport["BigQuery export to Bigtable"]
  BTExport --> BT
  API --> BQ["BigQuery feature registry + query embeddings"]
  API --> Alloy["AlloyDB products + ScaNN + FTS"]
  API --> BT["Bigtable online_features"]
  API --> Vertex["Vertex AI Endpoints"]
  API --> PubSub["Pub/Sub live events"]
  PubSub --> BQLive["BigQuery live_events"]
  BQLive --> CQ["BigQuery continuous query"]
  CQ --> BT
```

## Ownership

- BigQuery owns the copied theLook tables, enrichment, embeddings, feature
  definitions, training sets, and online-sync SQL.
- The AlloyDB loader job owns copying enriched product content plus embeddings into
  the serving catalog artifact.
- AlloyDB owns hybrid candidate retrieval after that loader has run.
- Bigtable owns online point lookups keyed as `user#...` and `item#...`.
- Vertex AI owns ranking, pricing, and coupon scoring endpoints.
- Pub/Sub and BigQuery continuous queries power the live-reaction demo.

## Runtime Boundary

The API never computes feature definitions in application code. It reads the online
rows, sends candidates and features to Vertex AI, enforces pricing floors, and returns
trace/freshness metadata to the UI.
