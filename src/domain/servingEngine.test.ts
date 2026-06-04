import { describe, expect, it } from 'vitest'
import {
  applyLiveEvent,
  buildTrainingExample,
  createFreshnessSummary,
  runServingPipeline,
} from './servingEngine'
import {
  catalog,
  createInitialFeatureStore,
  featureHistory,
  users,
} from '../data/retailDemoData'

const now = new Date('2026-06-04T17:00:00.000Z')

describe('retail serving engine', () => {
  it('runs the same retrieve-fetch-score pipeline for all three use cases', () => {
    const featureStore = createInitialFeatureStore(now)
    const useCases = ['recommendations', 'search', 'pricing'] as const

    for (const useCase of useCases) {
      const decision = runServingPipeline({
        catalog,
        featureStore,
        userId: users[0].id,
        useCase,
        query: 'trail jacket for rainy commute',
        category: 'Outerwear',
        maxPrice: 150,
        productId: 'p-trail-jacket',
        now,
      })

      expect(decision.trace.map((stage) => stage.service)).toEqual([
        'BigQuery',
        'AlloyDB ScaNN',
        'Bigtable',
        'Vertex AI',
      ])
      expect(decision.trace.every((stage) => stage.latencyMs > 0)).toBe(true)
      expect(decision.trace.some((stage) => stage.operation.includes('scan'))).toBe(false)
      expect(decision.results.length).toBeGreaterThan(0)
      expect(decision.freshness.maxStalenessSeconds).toBeLessThanOrEqual(120)
    }
  })

  it('returns no candidates for an empty catalog without skipping trace output', () => {
    const featureStore = createInitialFeatureStore(now)

    const decision = runServingPipeline({
      catalog: [],
      featureStore,
      userId: users[0].id,
      useCase: 'search',
      query: 'trail jacket',
      category: 'Outerwear',
      maxPrice: 150,
      productId: 'p-trail-jacket',
      now,
    })

    expect(decision.results).toEqual([])
    expect(decision.trace).toHaveLength(4)
    expect(decision.debugSql).toContain('LIMIT 100')
  })

  it('handles an empty search query without text-rank leakage', () => {
    const featureStore = createInitialFeatureStore(now)

    const decision = runServingPipeline({
      catalog,
      featureStore,
      userId: users[0].id,
      useCase: 'search',
      query: '',
      category: 'Outerwear',
      maxPrice: 150,
      productId: 'p-trail-jacket',
      now,
    })

    expect(decision.results.length).toBeGreaterThan(0)
    expect(decision.results.every((result) => result.retrieval.textRank === 0)).toBe(true)
  })

  it('throws actionable errors for unknown user and product feature rows', () => {
    const featureStore = createInitialFeatureStore(now)

    expect(() =>
      runServingPipeline({
        catalog,
        featureStore,
        userId: 'u-missing',
        useCase: 'search',
        query: 'trail jacket',
        category: 'Outerwear',
        maxPrice: 150,
        productId: 'p-trail-jacket',
        now,
      }),
    ).toThrow('Missing online feature row for user#u-missing')

    expect(() =>
      runServingPipeline({
        catalog,
        featureStore,
        userId: users[0].id,
        useCase: 'pricing',
        query: '',
        category: 'Outerwear',
        maxPrice: 150,
        productId: 'p-missing',
        now,
      }),
    ).toThrow('Missing online feature row for item#p-missing')
  })

  it('keeps high keyword-rank matches in hybrid search before truncation', () => {
    const featureStore = createInitialFeatureStore(now)

    const decision = runServingPipeline({
      catalog,
      featureStore,
      userId: users[0].id,
      useCase: 'search',
      query: 'trail jacket',
      category: 'Outerwear',
      maxPrice: 160,
      productId: 'p-urban-fleece',
      now,
    })

    const [topResult] = decision.results

    expect(topResult.product.id).toBe('p-trail-jacket')
    expect(topResult.retrieval.vectorSimilarity).toBeLessThan(
      decision.results[1].retrieval.vectorSimilarity,
    )
    expect(topResult.retrieval.textRank).toBeGreaterThan(
      decision.results[1].retrieval.textRank,
    )
    expect(topResult.retrieval.combinedScore).toBeGreaterThan(
      decision.results[1].retrieval.combinedScore,
    )
    expect(decision.debugSql).toContain('combined_score')
  })

  it('enforces pricing floors and emits an explainable coupon tier', () => {
    const featureStore = createInitialFeatureStore(now)

    const decision = runServingPipeline({
      catalog,
      featureStore,
      userId: 'u-price-sensitive',
      useCase: 'pricing',
      query: '',
      category: 'Outerwear',
      maxPrice: 160,
      productId: 'p-trail-jacket',
      now,
    })

    const [priced] = decision.results
    const floor = priced.product.cost * 1.18

    expect(priced.priceDecision).toBeDefined()
    expect(priced.priceDecision?.finalPrice).toBeGreaterThanOrEqual(floor)
    expect(priced.priceDecision?.couponTier).toBe('15% loyalty coupon')
    expect(priced.explanation).toContain('inventory pressure')
    expect(priced.explanation).toContain('price tier')
  })

  it('updates feature values and timestamps when a live event arrives', () => {
    const featureStore = createInitialFeatureStore(now)
    const before = runServingPipeline({
      catalog,
      featureStore,
      userId: users[0].id,
      useCase: 'pricing',
      query: '',
      category: 'Outerwear',
      maxPrice: 160,
      productId: 'p-trail-jacket',
      now,
    })

    const nextStore = applyLiveEvent(featureStore, {
      productId: 'p-trail-jacket',
      type: 'product_viewed',
      occurredAt: new Date(now.getTime() + 15_000),
    })
    const after = runServingPipeline({
      catalog,
      featureStore: nextStore,
      userId: users[0].id,
      useCase: 'pricing',
      query: '',
      category: 'Outerwear',
      maxPrice: 160,
      productId: 'p-trail-jacket',
      now: new Date(now.getTime() + 15_000),
    })

    expect(after.onlineFeatures.item.itemViews24h).toBe(
      before.onlineFeatures.item.itemViews24h + 1,
    )
    expect(after.freshness.maxStalenessSeconds).toBe(0)
    expect(after.results[0].priceDecision?.finalPrice).toBeGreaterThanOrEqual(
      before.results[0].priceDecision?.finalPrice ?? 0,
    )
  })

  it('marks stale online features when Bigtable cell timestamps miss the SLA', () => {
    const staleNow = new Date(now.getTime() + 180_000)
    const featureStore = createInitialFeatureStore(now)
    const summary = createFreshnessSummary(featureStore, 'p-trail-jacket', staleNow)

    expect(summary.maxStalenessSeconds).toBe(180)
    expect(summary.status).toBe('stale')
    expect(summary.rows).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          entityKey: 'item#p-trail-jacket',
          stalenessSeconds: 180,
          status: 'stale',
        }),
      ]),
    )
  })

  it('keeps features fresh exactly at the freshness SLA boundary', () => {
    const boundaryNow = new Date(now.getTime() + 120_000)
    const featureStore = createInitialFeatureStore(now)
    const summary = createFreshnessSummary(featureStore, 'p-trail-jacket', boundaryNow)

    expect(summary.maxStalenessSeconds).toBe(120)
    expect(summary.status).toBe('fresh')
  })

  it('applies live events immutably for independent request flows', () => {
    const featureStore = createInitialFeatureStore(now)
    const nextStore = applyLiveEvent(featureStore, {
      productId: 'p-trail-jacket',
      type: 'item_purchased',
      occurredAt: new Date(now.getTime() + 30_000),
    })

    expect(featureStore.items['p-trail-jacket'].itemUnitsSold7d).toBe(14)
    expect(nextStore.items['p-trail-jacket'].itemUnitsSold7d).toBe(15)
    expect(nextStore.items['p-trail-jacket'].itemInventoryOnHand).toBe(72)
  })

  it('extracts point-in-time training features without leaking later values', () => {
    const example = buildTrainingExample({
      featureHistory,
      userId: 'u-ada',
      productId: 'p-trail-jacket',
      labelEventAt: new Date('2026-06-04T15:30:00.000Z'),
    })

    expect(example.userFeatures.userOrderCount90d).toBe(5)
    expect(example.itemFeatures.itemViews24h).toBe(38)
    expect(example.featureCutoff.toISOString()).toBe('2026-06-04T15:30:00.000Z')
    expect(example.itemFeatures.itemUnitsSold7d).not.toBe(19)
  })
})
