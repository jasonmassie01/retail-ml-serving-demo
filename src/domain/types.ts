export type UseCase = 'recommendations' | 'search' | 'pricing'

export type FeatureStatus = 'fresh' | 'stale'

export type LiveEventType = 'product_viewed' | 'item_purchased'

export interface Product {
  id: string
  name: string
  brand: string
  category: string
  department: string
  sku: string
  retailPrice: number
  cost: number
  description: string
  contentText: string
  tags: readonly string[]
  embedding: readonly number[]
}

export interface DemoUser {
  id: string
  name: string
  segment: string
  priceTier: 'value' | 'balanced' | 'premium'
  categoryAffinity: readonly string[]
  couponPropensity: number
}

export interface OnlineUserFeatures {
  entityKey: string
  userAov30d: number
  userOrderCount90d: number
  userReturnRate: number
  userSessions7d: number
  userDaysSinceLastOrder: number
  userCategoryAffinity: readonly string[]
  userPriceTier: DemoUser['priceTier']
  couponPropensity: number
  cellTimestamp: Date
}

export interface OnlineItemFeatures {
  entityKey: string
  itemUnitsSold7d: number
  itemUnitsSold30d: number
  itemViews24h: number
  itemViewToPurchaseRate: number
  itemReturnRate: number
  itemAvgSalePrice: number
  itemInventoryOnHand: number
  itemDaysInStock: number
  itemRevenue30d: number
  demandSlope24h: number
  inventoryPressure: number
  cellTimestamp: Date
}

export interface FeatureStore {
  users: Record<string, OnlineUserFeatures>
  items: Record<string, OnlineItemFeatures>
  eventLog: readonly LiveEvent[]
}

export interface HistoricalFeature<TFeatures> {
  at: Date
  features: TFeatures
}

export interface FeatureHistory {
  users: Record<string, readonly HistoricalFeature<OnlineUserFeatures>[]>
  items: Record<string, readonly HistoricalFeature<OnlineItemFeatures>[]>
}

export interface LiveEvent {
  productId: string
  type: LiveEventType
  occurredAt: Date
}

export interface ServingTraceStage {
  service: 'BigQuery' | 'AlloyDB ScaNN' | 'Bigtable' | 'Vertex AI'
  operation: string
  latencyMs: number
}

export interface RetrievalScore {
  vectorSimilarity: number
  textRank: number
  combinedScore: number
}

export interface PriceDecision {
  listPrice: number
  finalPrice: number
  floorPrice: number
  couponTier: string
}

export interface ServingResult {
  product: Product
  retrieval: RetrievalScore
  modelScore: number
  explanation: string
  priceDecision?: PriceDecision
}

export interface FreshnessRow {
  entityKey: string
  service: 'Bigtable'
  cellTimestamp: Date
  stalenessSeconds: number
  status: FeatureStatus
}

export interface FreshnessSummary {
  rows: readonly FreshnessRow[]
  maxStalenessSeconds: number
  status: FeatureStatus
}

export interface ServingDecision {
  useCase: UseCase
  results: readonly ServingResult[]
  trace: readonly ServingTraceStage[]
  onlineFeatures: {
    user: OnlineUserFeatures
    item: OnlineItemFeatures
  }
  freshness: FreshnessSummary
  debugSql: string
  eventCount: number
}

export interface RunServingInput {
  catalog: readonly Product[]
  featureStore: FeatureStore
  userId: string
  useCase: UseCase
  query: string
  category: string
  maxPrice: number
  productId: string
  now: Date
}

export interface TrainingExampleInput {
  featureHistory: FeatureHistory
  userId: string
  productId: string
  labelEventAt: Date
}

export interface TrainingExample {
  userFeatures: OnlineUserFeatures
  itemFeatures: OnlineItemFeatures
  featureCutoff: Date
}
