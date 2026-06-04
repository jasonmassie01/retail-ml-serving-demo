# Retail ML Serving Demo: Architecture Findings

## Source Inputs

- Google Doc: `retail-ml-serving-demo-spec`, version 0.3, dated 2026-06-04.
- Local repo state: React + TypeScript + Vite starter app.
- User constraint: publish to GitHub, but do not deploy to GCP.
- Scope constraint for this pass: architecture findings only; no `src` or package edits.

## Recommended Local Demo Scope

Build a local, browser-only demo that emulates the locked Google Cloud architecture with
deterministic in-repo data and model functions. The pitch should remain the same as the
spec: recommendations, search ranking, and dynamic pricing/coupons are all the same
retrieve -> feature fetch -> score/rank pipeline, parameterized three ways.

The demo should not pretend to call BigQuery, AlloyDB, Bigtable, Vertex AI, Pub/Sub, or
GCS. Instead, label each local layer as an emulator of the corresponding production
layer:

- Offline store emulator: deterministic feature snapshots and feature history.
- Catalog/vector store emulator: product catalog with normalized embedding arrays,
  text tokens, structured filters, and hybrid scoring.
- Online feature store emulator: entity-keyed feature rows with compute timestamps,
  cell timestamps, freshness SLA, and stale-read state.
- Serving emulator: one unified pipeline that accepts a use case, retrieves candidates
  when applicable, fetches user/item/context features, scores candidates, and returns
  an auditable decision.
- Live stream emulator: a local event simulator that changes item views, demand slope,
  inventory pressure, and price/recommendation outputs in real time.

The first viewport should be the working demo, not a marketing page. Recommended UI:

- Left rail or top tabs for `Recommendations`, `Search Ranking`, and `Pricing + Coupon`.
- Main decision panel showing the selected use case output.
- Shared pipeline trace showing candidate source, fetched rows, model inputs, score,
  business rules, and final decision.
- Freshness panel showing feature compute timestamp, cell timestamp, decision timestamp,
  `staleness_seconds`, and SLA status.
- Debug panel for hybrid score components, model feature vector, latency budget, and
  simulated store names.

Recommended data scale for a GitHub demo:

- 40-80 products across apparel categories with generated descriptions and local image
  placeholders or checked-in static images.
- 6-12 users with clear behavioral profiles.
- 100-300 historical events/orders sufficient to produce non-trivial feature values.
- 10-30 live events generated during the session without external services.

## Core Data Contracts

Use explicit TypeScript contracts so every UI panel and test shares the same surface.
The implementation can store fixtures as `.ts` or `.json`, but the runtime should
normalize into these shapes.

```ts
type EntityType = 'user' | 'item'
type UseCase = 'recommendations' | 'search' | 'pricing'

type Product = {
  productId: string
  name: string
  brand: string
  category: string
  department: string
  sku: string
  retailPrice: number
  cost: number
  description: string
  imageUri: string
  contentText: string
  embedding: number[]
  searchTokens: string[]
  inStock: boolean
}

type FeatureValue = number | string | boolean | string[]

type FeatureRow = {
  rowKey: `${EntityType}#${string}`
  entityType: EntityType
  entityId: string
  values: Record<string, FeatureValue>
  computedAt: string
  cellTimestamp: string
  freshnessSlaSeconds: number
}

type FeatureRegistryEntry = {
  featureName: string
  entityType: EntityType
  sourceTable: string
  fieldName: string
  onlineQualifier: string
  dataType: 'number' | 'string' | 'boolean' | 'string[]'
  freshnessSlaSeconds: number
}

type RequestContext = {
  useCase: UseCase
  userId: string
  query?: string
  seedProductId?: string
  productId?: string
  filters?: {
    category?: string
    maxPrice?: number
    inStockOnly?: boolean
  }
  now: string
}

type Candidate = {
  productId: string
  source: 'vector' | 'text' | 'hybrid' | 'direct'
  vectorSimilarity?: number
  textRank?: number
  retrievalScore: number
}

type ModelScore = {
  productId: string
  modelName: 'ranker' | 'search-reranker' | 'pricing-elasticity' | 'coupon-propensity'
  score: number
  featureVector: Record<string, FeatureValue>
  explanation: string[]
}

type Decision = {
  requestId: string
  useCase: UseCase
  candidates: Candidate[]
  scores: ModelScore[]
  results: Array<{
    productId: string
    rank?: number
    price?: number
    coupon?: {
      tier: 'none' | 'small' | 'medium' | 'large'
      percentOff: number
    }
    reasons: string[]
  }>
  timestamps: {
    featureComputedAt: string
    featureCellTimestamp: string
    decisionAt: string
    stalenessSeconds: number
  }
  latenciesMs: {
    candidateRetrieval: number
    featureFetch: number
    modelScoring: number
    total: number
  }
}

type LiveEvent = {
  eventId: string
  eventType: 'product_view' | 'add_to_cart' | 'purchase' | 'return'
  userId: string
  productId: string
  occurredAt: string
  quantity?: number
}
```

Important contract details:

- Product embeddings should be fixed length and L2-normalized in fixtures or startup
  normalization. The doc calls for 1536 dimensions in production; local fixtures can use
  a smaller dimension only if the UI labels this as local compression.
- Row keys must match `{entity_type}#{entity_id}`, for example `user#123` and
  `item#456`, so the local feature-store story matches Bigtable semantics.
- Feature freshness must be first-class, not hidden in helper code.
- Search retrieval must blend vector and text scores before truncation so keyword-only
  matches are not dropped too early.
- Pricing must enforce business bounds: never price below `cost + marginFloor`.

## Risk Points

- Cloud-to-local mismatch: the spec is a cloud architecture, but the GitHub artifact is
  local-only. The README and UI must clearly say "emulates" and avoid claiming live GCP
  services are running.
- Model credibility: deterministic scoring functions can look fake if explanations are
  vague. Keep feature vectors visible and make score math inspectable.
- Hybrid search correctness: vector-only limits can hide high text-rank matches. Use a
  blended score over a broad candidate set before final limiting.
- Feature-store skew: do not compute user/item quantities in separate UI paths. Define
  feature fixtures and registry once, then route all use cases through the same fetcher.
- Freshness theater: live updates must update timestamps, stale flags, and decisions
  together. A moving chart without changed feature rows will undercut the demo.
- Pricing safety: dynamic pricing needs visible floor/ceiling rules so the demo does not
  recommend unrealistic or below-cost prices.
- Dataset realism: theLook is static and remote in the spec. Local data should be
  synthetic but shaped like theLook tables, with enough events/orders to justify the
  feature values.
- Publishability: no secrets, no required GCP credentials, no hidden network calls, and
  no deployment prerequisites.
- Test surface: `vitest` is installed but `package.json` currently has no test script.
  Later implementation should add a test command and verify it in CI before GitHub
  publication.

## Verification Checklist

CHECK-01: [PENDING] App builds locally with `npm run build` and no TypeScript errors.

CHECK-02: [PENDING] Lint passes with `npm run lint`.

CHECK-03: [PENDING] Unit tests cover the shared pipeline happy path for all three use
cases.

CHECK-04: [PENDING] Unit tests cover invalid inputs: empty query, unknown user,
unknown product, malformed filter, and no candidates.

CHECK-05: [PENDING] Unit tests cover zero/empty states: empty catalog, empty feature
store, empty event stream, and zero inventory.

CHECK-06: [PENDING] Unit tests cover feature freshness boundaries: fresh, exactly at
SLA, and stale.

CHECK-07: [PENDING] Unit tests prove hybrid retrieval blends vector and text scores
before truncation.

CHECK-08: [PENDING] Unit tests prove pricing never returns a price below the configured
margin floor.

CHECK-09: [PENDING] Live-event simulation changes at least one feature row, timestamp,
staleness value, and downstream recommendation or pricing decision.

CHECK-10: [PENDING] Browser check confirms the first viewport is the actual demo and
not the Vite starter screen.

CHECK-11: [PENDING] Browser check confirms desktop and mobile layouts have no text
overlap, clipped controls, or unreadable debug panels.

CHECK-12: [PENDING] README documents local-only setup, architecture mapping, demo
script, and GitHub publishing steps without GCP deployment instructions.

CHECK-13: [PENDING] Security check confirms no API keys, service-account files,
tokens, or credential-dependent code paths are committed.

CHECK-14: [PENDING] GitHub publish check confirms repository has a clean install path:
`npm ci`, `npm run lint`, `npm run build`, and tests.
