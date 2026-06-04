import { describe, expect, it, vi } from 'vitest'
import { createInitialFeatureStore } from '../data/retailDemoData'
import { createServingClient } from './servingClient'

const now = new Date('2026-06-04T17:00:00.000Z')

describe('serving client', () => {
  it('uses the local emulator when no API base URL is configured', async () => {
    const client = createServingClient()
    const featureStore = createInitialFeatureStore(now)

    const decision = await client.serve({
      activeUseCase: 'search',
      query: 'trail jacket',
      selectedProductId: 'p-trail-jacket',
      selectedUserId: 'u-ada',
      featureStore,
      now,
    })

    expect(decision.serviceMode).toBe('emulator')
    expect(decision.results[0].product.id).toBe('p-trail-jacket')
    expect(decision.freshness.rows[0].cellTimestamp).toBeInstanceOf(Date)
  })

  it('posts serving requests to a live API and revives timestamps', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        serviceMode: 'live',
        useCase: 'search',
        results: [],
        trace: [],
        onlineFeatures: {
          user: {
            entityKey: 'user#u-ada',
            userAov30d: 81,
            userOrderCount90d: 5,
            userReturnRate: 0.03,
            userSessions7d: 3,
            userDaysSinceLastOrder: 4,
            userCategoryAffinity: ['Outerwear'],
            userPriceTier: 'balanced',
            couponPropensity: 0.72,
            cellTimestamp: '2026-06-04T17:00:00.000Z',
          },
          item: {
            entityKey: 'item#p-trail-jacket',
            itemUnitsSold7d: 14,
            itemUnitsSold30d: 52,
            itemViews24h: 38,
            itemViewToPurchaseRate: 0.23,
            itemReturnRate: 0.04,
            itemAvgSalePrice: 121,
            itemInventoryOnHand: 73,
            itemDaysInStock: 21,
            itemRevenue30d: 6120,
            demandSlope24h: 0.42,
            inventoryPressure: 5.2,
            cellTimestamp: '2026-06-04T17:00:00.000Z',
          },
        },
        freshness: {
          rows: [
            {
              entityKey: 'item#p-trail-jacket',
              service: 'Bigtable',
              cellTimestamp: '2026-06-04T17:00:00.000Z',
              stalenessSeconds: 0,
              status: 'fresh',
            },
          ],
          maxStalenessSeconds: 0,
          status: 'fresh',
        },
        debugSql: 'SELECT ...',
        eventCount: 0,
      }),
    })
    const client = createServingClient('https://retail-api.example.com', fetchMock)

    const decision = await client.serve({
      activeUseCase: 'search',
      query: 'trail jacket',
      selectedProductId: 'p-trail-jacket',
      selectedUserId: 'u-ada',
      featureStore: createInitialFeatureStore(now),
      now,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'https://retail-api.example.com/api/serve',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"useCase":"search"'),
      }),
    )
    expect(decision.serviceMode).toBe('live')
    expect(decision.freshness.rows[0].cellTimestamp).toBeInstanceOf(Date)
  })

  it('publishes live events through the API when configured', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        eventId: 'events/1',
        published: true,
        updatedFeature: {
          entityKey: 'item#p-trail-jacket',
          values: { itemViews24h: 39 },
          cellTimestamp: '2026-06-04T17:00:15.000Z',
          stalenessSeconds: 0,
          status: 'fresh',
        },
      }),
    })
    const client = createServingClient('https://retail-api.example.com', fetchMock)

    const response = await client.publishEvent({
      productId: 'p-trail-jacket',
      eventType: 'product_viewed',
      occurredAt: new Date('2026-06-04T17:00:15.000Z'),
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'https://retail-api.example.com/api/events',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"productId":"p-trail-jacket"'),
      }),
    )
    expect(response.updatedFeature.cellTimestamp).toBeInstanceOf(Date)
  })

  it('throws a useful error when the live API returns a failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => 'missing live settings',
      json: async () => ({}),
    })
    const client = createServingClient('https://retail-api.example.com', fetchMock)

    await expect(
      client.serve({
        activeUseCase: 'search',
        query: 'trail jacket',
        selectedProductId: 'p-trail-jacket',
        selectedUserId: 'u-ada',
        featureStore: createInitialFeatureStore(now),
        now,
      }),
    ).rejects.toThrow('missing live settings')
  })

  it('normalizes pricing decisions returned by the live API', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        serviceMode: 'live',
        useCase: 'pricing',
        results: [
          {
            product: {
              productId: 'p-trail-jacket',
              name: 'TrailShield Rain Jacket',
              brand: 'Cymbal',
              category: 'Outerwear',
              department: 'Women',
              retailPrice: 129,
              cost: 72,
              description: 'Waterproof shell.',
            },
            retrieval: {
              vectorSimilarity: 0,
              textRank: 0,
              combinedScore: 0,
            },
            modelScore: 0.9,
            explanation: 'bounded price',
            priceDecision: {
              listPrice: 129,
              finalPrice: 118.5,
              floorPrice: 84.96,
              couponTier: '15% loyalty coupon',
            },
          },
        ],
        trace: [],
        onlineFeatures: {
          user: { entityKey: 'user#u-ada', values: {}, cellTimestamp: now.toISOString() },
          item: { entityKey: 'item#p-trail-jacket', values: {}, cellTimestamp: now.toISOString() },
        },
        freshness: {
          rows: [
            {
              entityKey: 'item#p-trail-jacket',
              service: 'Bigtable',
              cellTimestamp: now.toISOString(),
              stalenessSeconds: 181,
              status: 'stale',
            },
          ],
          maxStalenessSeconds: 181,
          status: 'stale',
        },
        debugSql: 'pricing = ...',
        eventCount: 2,
      }),
    })
    const client = createServingClient('https://retail-api.example.com/', fetchMock)

    const decision = await client.serve({
      activeUseCase: 'pricing',
      query: '',
      selectedProductId: 'p-trail-jacket',
      selectedUserId: 'u-ada',
      featureStore: createInitialFeatureStore(now),
      now,
    })

    expect(decision.results[0].priceDecision?.couponTier).toBe('15% loyalty coupon')
    expect(decision.freshness.status).toBe('stale')
    expect(fetchMock).toHaveBeenCalledWith(
      'https://retail-api.example.com/api/serve',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('returns a local event response when using emulator mode', async () => {
    const client = createServingClient()

    const response = await client.publishEvent({
      productId: 'p-trail-jacket',
      eventType: 'product_viewed',
      occurredAt: new Date('2026-06-04T17:00:15.000Z'),
    })

    expect(response.eventId).toBe('emulator-local')
    expect(response.updatedFeature.entityKey).toBe('item#p-trail-jacket')
    expect(response.updatedFeature.status).toBe('fresh')
  })
})
