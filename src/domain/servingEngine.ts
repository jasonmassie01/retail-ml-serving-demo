import type {
  FeatureStatus,
  FeatureStore,
  FreshnessSummary,
  LiveEvent,
  OnlineItemFeatures,
  PriceDecision,
  Product,
  RetrievalScore,
  RunServingInput,
  ServingDecision,
  ServingResult,
  ServingTraceStage,
  TrainingExample,
  TrainingExampleInput,
} from './types'

const FRESHNESS_SLA_SECONDS = 120

const HYBRID_SEARCH_SQL = `SELECT product_id, name, retail_price,
  (1.0 - (embedding <=> $1)) AS vector_similarity,
  ts_rank(fts, plainto_tsquery('english', $2)) AS text_rank,
  (((1.0 - (embedding <=> $1)) * 0.7)
    + (ts_rank(fts, plainto_tsquery('english', $2)) * 0.3)) AS combined_score
FROM products
WHERE retail_price < $3 AND category = $4
ORDER BY combined_score DESC
LIMIT 100;`

export function runServingPipeline(input: RunServingInput): ServingDecision {
  const userFeatures = getUserFeatures(input)
  const selectedItem = getItemFeatures(input.featureStore, input.productId)
  const candidates = retrieveCandidates(input)
  const results = candidates.map((product) => scoreProduct(input, product))
  const sorted = results.toSorted((left, right) => right.modelScore - left.modelScore)

  return {
    useCase: input.useCase,
    results: sorted.slice(0, input.useCase === 'pricing' ? 1 : 3),
    trace: createTrace(input.useCase),
    onlineFeatures: { user: userFeatures, item: selectedItem },
    freshness: createFreshnessSummary(input.featureStore, input.productId, input.now),
    debugSql: input.useCase === 'search' ? HYBRID_SEARCH_SQL : createDebugSql(input.useCase),
    eventCount: input.featureStore.eventLog.length,
  }
}

export function applyLiveEvent(store: FeatureStore, event: LiveEvent): FeatureStore {
  const current = store.items[event.productId]
  const itemViews24h = current.itemViews24h + (event.type === 'product_viewed' ? 1 : 0)
  const itemUnitsSold7d = current.itemUnitsSold7d + (event.type === 'item_purchased' ? 1 : 0)
  const demandSlope24h = Math.min(current.demandSlope24h + 0.06, 1)
  const itemInventoryOnHand = Math.max(
    current.itemInventoryOnHand - (event.type === 'item_purchased' ? 1 : 0),
    0,
  )
  const inventoryPressure = itemInventoryOnHand / Math.max(itemUnitsSold7d, 1)

  return {
    ...store,
    items: {
      ...store.items,
      [event.productId]: {
        ...current,
        itemViews24h,
        itemUnitsSold7d,
        itemUnitsSold30d: current.itemUnitsSold30d + 1,
        itemInventoryOnHand,
        itemViewToPurchaseRate: itemUnitsSold7d / Math.max(itemViews24h, 1),
        demandSlope24h,
        inventoryPressure,
        cellTimestamp: event.occurredAt,
      },
    },
    eventLog: [event, ...store.eventLog],
  }
}

export function createFreshnessSummary(
  store: FeatureStore,
  productId: string,
  now: Date,
): FreshnessSummary {
  const item = store.items[productId]
  const stalenessSeconds = secondsBetween(item.cellTimestamp, now)
  const status: FeatureStatus =
    stalenessSeconds > FRESHNESS_SLA_SECONDS ? 'stale' : 'fresh'
  const row = {
    entityKey: item.entityKey,
    service: 'Bigtable' as const,
    cellTimestamp: item.cellTimestamp,
    stalenessSeconds,
    status,
  }

  return {
    rows: [row],
    maxStalenessSeconds: stalenessSeconds,
    status,
  }
}

export function buildTrainingExample(input: TrainingExampleInput): TrainingExample {
  const userFeatures = latestAtOrBefore(
    input.featureHistory.users[input.userId],
    input.labelEventAt,
  )
  const itemFeatures = latestAtOrBefore(
    input.featureHistory.items[input.productId],
    input.labelEventAt,
  )

  return {
    userFeatures,
    itemFeatures,
    featureCutoff: input.labelEventAt,
  }
}

export function formatFreshness(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s fresh`
  }

  const status = seconds > FRESHNESS_SLA_SECONDS ? 'stale' : 'fresh'
  return `${Math.round(seconds / 60)}m ${status}`
}

function retrieveCandidates(input: RunServingInput): readonly Product[] {
  getUserFeatures(input)

  if (input.useCase === 'pricing') {
    getItemFeatures(input.featureStore, input.productId)
    return input.catalog.filter((product) => product.id === input.productId)
  }

  const filtered = input.catalog.filter((product) => {
    return product.category === input.category && product.retailPrice <= input.maxPrice
  })

  if (input.useCase === 'search') {
    return filtered
  }

  const user = input.featureStore.users[input.userId]
  return filtered.filter((product) => user.userCategoryAffinity.includes(product.category))
}

function scoreProduct(input: RunServingInput, product: Product): ServingResult {
  const retrieval = scoreRetrieval(input.query, product)
  const item = getItemFeatures(input.featureStore, product.id)
  const user = getUserFeatures(input)
  const affinityBonus = user.userCategoryAffinity.includes(product.category) ? 0.08 : 0
  const featureBoost = item.demandSlope24h * 0.12 + item.itemViewToPurchaseRate * 0.08
  const modelScore = roundScore(retrieval.combinedScore + affinityBonus + featureBoost)
  const priceDecision = input.useCase === 'pricing' ? priceProduct(product, item, user) : undefined

  return {
    product,
    retrieval,
    modelScore,
    priceDecision,
    explanation: explainDecision(product, item, user.userPriceTier, input.useCase),
  }
}

function scoreRetrieval(query: string, product: Product): RetrievalScore {
  const vectorSimilarity = cosineSimilarity(queryEmbedding(query), product.embedding)
  const textRank = textRankScore(query, product)
  const combinedScore = roundScore(vectorSimilarity * 0.7 + textRank * 0.3)

  return {
    vectorSimilarity: roundScore(vectorSimilarity),
    textRank: roundScore(textRank),
    combinedScore,
  }
}

function priceProduct(
  product: Product,
  item: OnlineItemFeatures,
  user: { couponPropensity: number; userPriceTier: string },
): PriceDecision {
  const demandLift = item.demandSlope24h * 0.09
  const overstockMarkdown = Math.min(item.inventoryPressure * 0.014, 0.12)
  const rawPrice = product.retailPrice * (1 + demandLift - overstockMarkdown)
  const floorPrice = product.cost * 1.18
  const finalPrice = Math.max(rawPrice, floorPrice)

  return {
    listPrice: product.retailPrice,
    finalPrice: roundMoney(finalPrice),
    floorPrice: roundMoney(floorPrice),
    couponTier: couponTier(user.couponPropensity, user.userPriceTier),
  }
}

function explainDecision(
  product: Product,
  item: OnlineItemFeatures,
  priceTier: string,
  useCase: string,
): string {
  if (useCase === 'search') {
    if (product.id === 'p-trail-jacket') {
      return 'keyword rank preserved while vector similarity stays in the blended score.'
    }

    return 'hybrid retrieval kept this item eligible before Vertex AI reranking.'
  }

  return `${product.category} affinity, inventory pressure ${item.inventoryPressure.toFixed(
    1,
  )}, demand slope ${item.demandSlope24h.toFixed(2)}, and ${priceTier} price tier.`
}

function createTrace(useCase: string): readonly ServingTraceStage[] {
  return [
    { service: 'BigQuery', operation: 'materialized feature definitions', latencyMs: 18 },
    { service: 'AlloyDB ScaNN', operation: `${useCase} candidate generation`, latencyMs: 22 },
    { service: 'Bigtable', operation: 'entity-keyed point lookups', latencyMs: 3 },
    { service: 'Vertex AI', operation: `${useCase} score/rank endpoint`, latencyMs: 31 },
  ]
}

function createDebugSql(useCase: string): string {
  if (useCase === 'pricing') {
    return 'pricing = bounded elasticity model; coupon = BQML boosted-tree propensity'
  }

  return 'recommendations = ScaNN seed candidates + Bigtable features + Vertex ranker'
}

function getUserFeatures(input: RunServingInput) {
  const userFeatures = input.featureStore.users[input.userId]
  if (!userFeatures) {
    throw new Error(`Missing online feature row for user#${input.userId}`)
  }

  return userFeatures
}

function getItemFeatures(store: FeatureStore, productId: string) {
  const itemFeatures = store.items[productId]
  if (!itemFeatures) {
    throw new Error(`Missing online feature row for item#${productId}`)
  }

  return itemFeatures
}

function queryEmbedding(query: string): readonly number[] {
  const text = query.toLowerCase()
  if (text.includes('trail') || text.includes('jacket')) {
    return [0.76, 0.23, 0.16, 0.12]
  }
  if (text.includes('run')) {
    return [0.18, 0.82, 0.26, 0.1]
  }
  return [0.4, 0.4, 0.3, 0.1]
}

function textRankScore(query: string, product: Product): number {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean)
  const haystack = `${product.name} ${product.description} ${product.tags.join(' ')}`.toLowerCase()
  const matches = tokens.filter((token) => haystack.includes(token)).length
  return tokens.length === 0 ? 0 : matches / tokens.length
}

function cosineSimilarity(left: readonly number[], right: readonly number[]): number {
  const dot = left.reduce((sum, value, index) => sum + value * right[index], 0)
  const leftMagnitude = Math.sqrt(left.reduce((sum, value) => sum + value * value, 0))
  const rightMagnitude = Math.sqrt(right.reduce((sum, value) => sum + value * value, 0))
  return dot / (leftMagnitude * rightMagnitude)
}

function couponTier(propensity: number, priceTier: string): string {
  if (propensity >= 0.85 || priceTier === 'value') {
    return '15% loyalty coupon'
  }
  if (propensity >= 0.65) {
    return '10% basket coupon'
  }
  return 'no coupon'
}

function latestAtOrBefore<TFeatures>(
  history: readonly { at: Date; features: TFeatures }[],
  cutoff: Date,
): TFeatures {
  const matches = history.filter((entry) => entry.at.getTime() <= cutoff.getTime())
  const latest = matches.toSorted((left, right) => right.at.getTime() - left.at.getTime())[0]
  return latest.features
}

function secondsBetween(start: Date, end: Date): number {
  return Math.max(Math.floor((end.getTime() - start.getTime()) / 1000), 0)
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100
}

function roundScore(value: number): number {
  return Math.round(value * 1000) / 1000
}
