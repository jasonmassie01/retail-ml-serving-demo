# Local Demo Plan

## Goal

Build a GitHub-publishable local demo for the retail ML serving spec without deploying
or provisioning GCP resources.

## Implementation Scope

- React + TypeScript app shell.
- Three use-case modes: recommendations, search ranking, dynamic pricing.
- Shared serving engine with deterministic fixtures.
- Live event emulator for product views.
- Observability rail for services, latencies, feature freshness, and event count.
- Debug SQL panel showing the hybrid retrieval query shape.
- Reference SQL for GCP architecture mapping.

## Verification Checklist

CHECK-01: [PASS] App has tests for all three shared pipeline use cases.

CHECK-02: [PASS] Search test proves keyword-rank matches are not lost to vector-only
truncation.

CHECK-03: [PASS] Pricing test proves business-floor enforcement and coupon tier output.

CHECK-04: [PASS] Live-event test proves feature values and timestamps update.

CHECK-05: [PASS] Freshness test proves stale state when the SLA is missed.

CHECK-06: [PASS] UI tests prove controls render, search runs, and live events mutate
state.

CHECK-07: [PASS] Browser QA confirms desktop and mobile layouts are readable.

CHECK-08: [PASS] Lint, coverage, and production build pass.

CHECK-09: [PENDING] GitHub repository is created and pushed.
