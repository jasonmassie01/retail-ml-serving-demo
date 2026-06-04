# Architecture

The source specification locks a Google Cloud architecture. This repo implements a local
demo of the same contracts without provisioning cloud resources.

## Cloud-To-Local Mapping

| Spec layer | Cloud service | Local implementation |
| --- | --- | --- |
| Offline feature store | BigQuery | deterministic feature history fixtures |
| Catalog and vectors | AlloyDB + ScaNN | product catalog, embeddings, text tokens |
| Online feature store | Bigtable | row-keyed feature objects with timestamps |
| Event stream | Pub/Sub -> BigQuery -> Bigtable | local event reducer |
| Model serving | Vertex AI Endpoints | deterministic scoring functions |
| Observability | query profile and freshness checks | trace rail, debug SQL, freshness panel |

## Unified Serving Flow

Every use case runs the same stages:

1. BigQuery-stage feature definitions are already materialized as local fixtures.
2. AlloyDB ScaNN-stage retrieval returns candidates or a direct pricing product.
3. Bigtable-stage reads fetch `user#...` and `item#...` feature rows.
4. Vertex AI-stage scoring ranks products or produces a bounded price/coupon decision.

The pipeline is implemented in `src/domain/servingEngine.ts`.

## Correctness Properties

- Hybrid retrieval blends vector similarity and text rank before final limiting.
- Pricing never returns a price below `cost * 1.18`.
- Feature freshness is based on Bigtable-style cell timestamps.
- Live events update feature values, timestamps, freshness, and downstream decisions.
- Point-in-time training examples read feature history at or before the label event.

## What Is Not Implemented

- Real GCP resources.
- Real Gemini embedding or image generation calls.
- Real Vertex AI Endpoints.
- BigQuery continuous queries.
- Bigtable export jobs.

Those surfaces are represented by the reference SQL in `infra/sql/` and by local
emulator code that preserves the same serving contracts.
