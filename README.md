# Retail ML Serving Demo

A local, publishable React + TypeScript demo for the retail ML serving architecture in
the source Google Doc. It shows one shared retrieve -> feature fetch -> score/rank
pipeline powering:

- recommendations
- search ranking
- dynamic pricing + coupons

The demo intentionally does **not** deploy to GCP or require GCP credentials. It emulates
the contracts for BigQuery, AlloyDB ScaNN, Bigtable, Pub/Sub, and Vertex AI with
deterministic in-repo data so reviewers can run it from GitHub.

![Retail ML Serving Demo concept](docs/assets/retail-ml-serving-demo-concept.png)

## What It Demonstrates

- BigQuery as the offline feature and embedding compute layer.
- AlloyDB + ScaNN as the catalog/vector/full-text candidate source.
- Bigtable-style row-keyed online features with cell timestamps and freshness SLA.
- Vertex AI-style model scoring for rankers, pricing, and coupon propensity.
- A live event stream emulator that updates item features and downstream decisions.
- Debug visibility for hybrid search SQL, score components, latencies, and freshness.

## Run Locally

```bash
npm ci
npm run dev
```

Then open the local Vite URL shown in the terminal.

## Validate

```bash
npm run lint
npm test
npm run test:coverage
npm run build
```

## Repo Guide

- `src/domain/servingEngine.ts` implements the shared serving pipeline.
- `src/data/retailDemoData.ts` contains deterministic products, users, online features,
  and point-in-time feature history.
- `src/components/` contains the app shell, results, navigation, and observability UI.
- `infra/sql/` contains reference SQL for the intended GCP architecture. These are
  examples only and are not invoked by the app.
- `docs/ARCHITECTURE.md` maps the local emulator to the locked cloud architecture.
- `docs/LOCAL_DEMO_PLAN.md` captures the build and verification plan.

## Local-Only Boundary

This repository avoids:

- service-account files
- GCP deployment commands
- live BigQuery, AlloyDB, Bigtable, Pub/Sub, or Vertex AI calls
- hidden network dependencies

The point is to make the serving story inspectable and runnable before any cloud
provisioning work.
