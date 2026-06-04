import { catalog } from '../data/retailDemoData'
import { runServingPipeline } from '../domain/servingEngine'
import type {
  FeatureStatus,
  FeatureStore,
  FreshnessRow,
  FreshnessSummary,
  LiveEventType,
  OnlineItemFeatures,
  OnlineUserFeatures,
  PriceDecision,
  Product,
  RetrievalScore,
  ServingDecision,
  ServingResult,
  ServingTraceStage,
  UseCase,
} from '../domain/types'

type ServiceMode = 'emulator' | 'live'

export type ClientServingDecision = ServingDecision & { serviceMode: ServiceMode }

interface ServeInput {
  activeUseCase: UseCase
  query: string
  selectedProductId: string
  selectedUserId: string
  featureStore: FeatureStore
  now: Date
}

interface PublishEventInput {
  productId: string
  eventType: LiveEventType
  occurredAt: Date
}

interface PublishedEvent {
  eventId: string
  published: boolean
  updatedFeature: {
    entityKey: string
    values: Record<string, unknown>
    cellTimestamp: Date
    stalenessSeconds: number
    status: FeatureStatus
  }
}

interface FetchLike {
  (input: string, init?: RequestInit): Promise<ResponseLike>
}

interface ResponseLike {
  ok: boolean
  status?: number
  text?: () => Promise<string>
  json: () => Promise<unknown>
}

interface ServingClient {
  serve(input: ServeInput): Promise<ClientServingDecision>
  publishEvent(input: PublishEventInput): Promise<PublishedEvent>
}

export function createServingClient(
  apiBaseUrl = '',
  fetcher: FetchLike = fetch,
): ServingClient {
  const normalizedBase = apiBaseUrl.replace(/\/$/, '')
  if (!normalizedBase) {
    return createEmulatorClient()
  }

  return {
    async serve(input) {
      const body = await postJson(fetcher, `${normalizedBase}/api/serve`, {
        useCase: input.activeUseCase,
        userId: input.selectedUserId,
        query: input.query,
        category: 'Outerwear',
        maxPrice: 160,
        productId: input.selectedProductId,
      })
      return reviveServingDecision(body)
    },
    async publishEvent(input) {
      const body = await postJson(fetcher, `${normalizedBase}/api/events`, {
        productId: input.productId,
        eventType: input.eventType,
        occurredAt: input.occurredAt.toISOString(),
      })
      return revivePublishedEvent(body)
    },
  }
}

function createEmulatorClient(): ServingClient {
  return {
    async serve(input) {
      return {
        ...runServingPipeline({
          catalog,
          featureStore: input.featureStore,
          userId: input.selectedUserId,
          useCase: input.activeUseCase,
          query: input.query,
          category: 'Outerwear',
          maxPrice: 160,
          productId: input.selectedProductId,
          now: input.now,
        }),
        serviceMode: 'emulator',
      }
    },
    async publishEvent(input) {
      return {
        eventId: 'emulator-local',
        published: true,
        updatedFeature: {
          entityKey: `item#${input.productId}`,
          values: {},
          cellTimestamp: input.occurredAt,
          stalenessSeconds: 0,
          status: 'fresh',
        },
      }
    },
  }
}

async function postJson(
  fetcher: FetchLike,
  url: string,
  body: Record<string, unknown>,
): Promise<unknown> {
  const response = await fetcher(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = response.text ? await response.text() : `HTTP ${response.status ?? ''}`
    throw new Error(`Serving API request failed: ${detail}`)
  }
  return response.json()
}

function reviveServingDecision(value: unknown): ClientServingDecision {
  const body = asRecord(value)
  const online = asRecord(body.onlineFeatures)
  const freshness = reviveFreshness(body.freshness)

  return {
    serviceMode: asServiceMode(body.serviceMode),
    useCase: asUseCase(body.useCase),
    results: asArray(body.results).map(reviveResult),
    trace: asArray(body.trace).map(reviveTraceStage),
    onlineFeatures: {
      user: reviveUserFeature(online.user),
      item: reviveItemFeature(online.item),
    },
    freshness,
    debugSql: asString(body.debugSql),
    eventCount: asNumber(body.eventCount),
  }
}

function revivePublishedEvent(value: unknown): PublishedEvent {
  const body = asRecord(value)
  const updated = asRecord(body.updatedFeature)
  return {
    eventId: asString(body.eventId),
    published: asBoolean(body.published),
    updatedFeature: {
      entityKey: asString(updated.entityKey),
      values: asRecord(updated.values),
      cellTimestamp: asDate(updated.cellTimestamp),
      stalenessSeconds: asNumber(updated.stalenessSeconds),
      status: asFeatureStatus(updated.status),
    },
  }
}

function reviveResult(value: unknown): ServingResult {
  const result = asRecord(value)
  return {
    product: reviveProduct(result.product),
    retrieval: reviveRetrieval(result.retrieval),
    modelScore: asNumber(result.modelScore),
    explanation: asString(result.explanation),
    priceDecision: result.priceDecision ? revivePrice(result.priceDecision) : undefined,
  }
}

function reviveProduct(value: unknown): Product {
  const product = asRecord(value)
  const productId = asString(product.productId || product.id)
  return {
    id: productId,
    name: asString(product.name),
    brand: asString(product.brand),
    category: asString(product.category),
    department: asString(product.department),
    sku: productId,
    retailPrice: asNumber(product.retailPrice),
    cost: asNumber(product.cost),
    description: asString(product.description),
    contentText: asString(product.description),
    tags: [],
    embedding: [],
  }
}

function reviveRetrieval(value: unknown): RetrievalScore {
  const retrieval = asRecord(value)
  return {
    vectorSimilarity: asNumber(retrieval.vectorSimilarity),
    textRank: asNumber(retrieval.textRank),
    combinedScore: asNumber(retrieval.combinedScore),
  }
}

function revivePrice(value: unknown): PriceDecision {
  const price = asRecord(value)
  return {
    listPrice: asNumber(price.listPrice),
    finalPrice: asNumber(price.finalPrice),
    floorPrice: asNumber(price.floorPrice),
    couponTier: asString(price.couponTier),
  }
}

function reviveTraceStage(value: unknown): ServingTraceStage {
  const stage = asRecord(value)
  return {
    service: asString(stage.service) as ServingTraceStage['service'],
    operation: asString(stage.operation),
    latencyMs: asNumber(stage.latencyMs),
  }
}

function reviveFreshness(value: unknown): FreshnessSummary {
  const summary = asRecord(value)
  const rows = asArray(summary.rows).map(reviveFreshnessRow)
  return {
    rows,
    maxStalenessSeconds: asNumber(summary.maxStalenessSeconds),
    status: asFeatureStatus(summary.status),
  }
}

function reviveFreshnessRow(value: unknown): FreshnessRow {
  const row = asRecord(value)
  return {
    entityKey: asString(row.entityKey),
    service: 'Bigtable',
    cellTimestamp: asDate(row.cellTimestamp),
    stalenessSeconds: asNumber(row.stalenessSeconds),
    status: asFeatureStatus(row.status),
  }
}

function reviveUserFeature(value: unknown): OnlineUserFeatures {
  const row = asRecord(value)
  const values = featureValues(row)
  return {
    entityKey: asString(row.entityKey),
    userAov30d: numberFrom(values, 'userAov30d', 'user_aov_30d'),
    userOrderCount90d: numberFrom(values, 'userOrderCount90d', 'user_order_count_90d'),
    userReturnRate: numberFrom(values, 'userReturnRate', 'user_return_rate'),
    userSessions7d: numberFrom(values, 'userSessions7d', 'user_sessions_7d'),
    userDaysSinceLastOrder: numberFrom(
      values,
      'userDaysSinceLastOrder',
      'user_days_since_last_order',
    ),
    userCategoryAffinity: stringArrayFrom(values, 'userCategoryAffinity', 'user_category_affinity'),
    userPriceTier: priceTierFrom(values),
    couponPropensity: numberFrom(values, 'couponPropensity', 'coupon_propensity'),
    cellTimestamp: asDate(row.cellTimestamp),
  }
}

function reviveItemFeature(value: unknown): OnlineItemFeatures {
  const row = asRecord(value)
  const values = featureValues(row)
  return {
    entityKey: asString(row.entityKey),
    itemUnitsSold7d: numberFrom(values, 'itemUnitsSold7d', 'item_units_sold_7d'),
    itemUnitsSold30d: numberFrom(values, 'itemUnitsSold30d', 'item_units_sold_30d'),
    itemViews24h: numberFrom(values, 'itemViews24h', 'item_views_24h'),
    itemViewToPurchaseRate: numberFrom(
      values,
      'itemViewToPurchaseRate',
      'item_view_to_purchase_rate',
    ),
    itemReturnRate: numberFrom(values, 'itemReturnRate', 'item_return_rate'),
    itemAvgSalePrice: numberFrom(values, 'itemAvgSalePrice', 'item_avg_sale_price'),
    itemInventoryOnHand: numberFrom(values, 'itemInventoryOnHand', 'item_inventory_on_hand'),
    itemDaysInStock: numberFrom(values, 'itemDaysInStock', 'item_days_in_stock'),
    itemRevenue30d: numberFrom(values, 'itemRevenue30d', 'item_revenue_30d'),
    demandSlope24h: numberFrom(values, 'demandSlope24h', 'demand_slope_24h'),
    inventoryPressure: numberFrom(values, 'inventoryPressure', 'inventory_pressure'),
    cellTimestamp: asDate(row.cellTimestamp),
  }
}

function featureValues(row: Record<string, unknown>): Record<string, unknown> {
  return row.values ? asRecord(row.values) : row
}

function numberFrom(values: Record<string, unknown>, ...keys: string[]): number {
  for (const key of keys) {
    const value = values[key]
    if (typeof value === 'number') {
      return value
    }
    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }
  }
  return 0
}

function stringArrayFrom(values: Record<string, unknown>, ...keys: string[]): readonly string[] {
  for (const key of keys) {
    const value = values[key]
    if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
      return value
    }
  }
  return []
}

function priceTierFrom(values: Record<string, unknown>): OnlineUserFeatures['userPriceTier'] {
  const tier = asString(values.userPriceTier || values.user_price_tier)
  if (tier === 'value' || tier === 'premium') {
    return tier
  }
  return 'balanced'
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function asArray(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : []
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number {
  return typeof value === 'number' ? value : 0
}

function asBoolean(value: unknown): boolean {
  return typeof value === 'boolean' ? value : false
}

function asDate(value: unknown): Date {
  return value instanceof Date ? value : new Date(asString(value))
}

function asServiceMode(value: unknown): ServiceMode {
  return value === 'live' ? 'live' : 'emulator'
}

function asUseCase(value: unknown): UseCase {
  if (value === 'search' || value === 'pricing') {
    return value
  }
  return 'recommendations'
}

function asFeatureStatus(value: unknown): FeatureStatus {
  return value === 'stale' ? 'stale' : 'fresh'
}
