import type {
  DemoUser,
  FeatureHistory,
  FeatureStore,
  OnlineItemFeatures,
  OnlineUserFeatures,
  Product,
} from '../domain/types'

export const catalog: readonly Product[] = [
  {
    id: 'p-trail-jacket',
    name: 'TrailShield Rain Jacket',
    brand: 'Cymbal Outfitters',
    category: 'Outerwear',
    department: 'Women',
    sku: 'OUT-RAIN-1536',
    retailPrice: 128,
    cost: 78,
    description: 'Waterproof shell built for trail runs, wet commutes, and packable travel.',
    contentText: 'TrailShield Rain Jacket. Brand: Cymbal Outfitters. Outerwear trail jacket.',
    tags: ['trail', 'jacket', 'rain', 'waterproof', 'commute'],
    embedding: [0.54, 0.45, 0.32, 0.18],
  },
  {
    id: 'p-urban-fleece',
    name: 'UrbanFlow Fleece Hoodie',
    brand: 'North Ledger',
    category: 'Outerwear',
    department: 'Men',
    sku: 'OUT-FLC-2048',
    retailPrice: 118,
    cost: 61,
    description: 'Soft commuter fleece with jacket-like warmth and an urban profile.',
    contentText: 'UrbanFlow Fleece Hoodie. Brand: North Ledger. Outerwear commuter fleece.',
    tags: ['urban', 'fleece', 'hoodie', 'commute'],
    embedding: [0.76, 0.23, 0.16, 0.12],
  },
  {
    id: 'p-denim-jacket',
    name: 'Selvedge Denim Trucker',
    brand: 'Line & Loom',
    category: 'Outerwear',
    department: 'Unisex',
    sku: 'OUT-DNM-4096',
    retailPrice: 142,
    cost: 82,
    description: 'Structured denim layer for weekend styling and mild weather.',
    contentText: 'Selvedge Denim Trucker. Brand: Line & Loom. Outerwear denim jacket.',
    tags: ['denim', 'jacket', 'weekend', 'structured'],
    embedding: [0.42, 0.36, 0.31, 0.24],
  },
  {
    id: 'p-run-short',
    name: 'PaceWeave Running Short',
    brand: 'Cymbal Active',
    category: 'Activewear',
    department: 'Women',
    sku: 'ACT-SHT-8192',
    retailPrice: 64,
    cost: 29,
    description: 'Lightweight short with quick-dry fabric for daily training.',
    contentText: 'PaceWeave Running Short. Brand: Cymbal Active. Activewear running.',
    tags: ['running', 'short', 'training', 'quick-dry'],
    embedding: [0.18, 0.82, 0.26, 0.1],
  },
]

export const users: readonly DemoUser[] = [
  {
    id: 'u-ada',
    name: 'Ada Rivera',
    segment: 'Loyal outdoor shopper',
    priceTier: 'balanced',
    categoryAffinity: ['Outerwear', 'Activewear'],
    couponPropensity: 0.64,
  },
  {
    id: 'u-price-sensitive',
    name: 'Mina Chen',
    segment: 'High coupon responder',
    priceTier: 'value',
    categoryAffinity: ['Outerwear'],
    couponPropensity: 0.91,
  },
]

export function createInitialFeatureStore(computedAt: Date): FeatureStore {
  return {
    users: {
      'u-ada': userFeatures(users[0], computedAt, 126, 6, 0.64),
      'u-price-sensitive': userFeatures(users[1], computedAt, 82, 5, 0.91),
    },
    items: {
      'p-trail-jacket': itemFeatures('p-trail-jacket', computedAt, 38, 14, 73, 0.12),
      'p-urban-fleece': itemFeatures('p-urban-fleece', computedAt, 61, 24, 31, 0.19),
      'p-denim-jacket': itemFeatures('p-denim-jacket', computedAt, 22, 8, 54, 0.04),
      'p-run-short': itemFeatures('p-run-short', computedAt, 84, 33, 48, 0.21),
    },
    eventLog: [],
  }
}

export const featureHistory: FeatureHistory = {
  users: {
    'u-ada': [
      { at: new Date('2026-06-04T14:00:00.000Z'), features: historicalUser(5) },
      { at: new Date('2026-06-04T16:00:00.000Z'), features: historicalUser(7) },
    ],
  },
  items: {
    'p-trail-jacket': [
      { at: new Date('2026-06-04T14:00:00.000Z'), features: historicalItem(38, 14) },
      { at: new Date('2026-06-04T16:00:00.000Z'), features: historicalItem(51, 19) },
    ],
  },
}

function userFeatures(
  user: DemoUser,
  timestamp: Date,
  aov: number,
  orders: number,
  propensity: number,
): OnlineUserFeatures {
  return {
    entityKey: `user#${user.id}`,
    userAov30d: aov,
    userOrderCount90d: orders,
    userReturnRate: 0.04,
    userSessions7d: 9,
    userDaysSinceLastOrder: 4,
    userCategoryAffinity: user.categoryAffinity,
    userPriceTier: user.priceTier,
    couponPropensity: propensity,
    cellTimestamp: timestamp,
  }
}

function itemFeatures(
  productId: string,
  timestamp: Date,
  views24h: number,
  sold7d: number,
  inventory: number,
  demandSlope: number,
): OnlineItemFeatures {
  const inventoryPressure = inventory / Math.max(sold7d, 1)

  return {
    entityKey: `item#${productId}`,
    itemUnitsSold7d: sold7d,
    itemUnitsSold30d: sold7d * 4,
    itemViews24h: views24h,
    itemViewToPurchaseRate: sold7d / Math.max(views24h, 1),
    itemReturnRate: 0.03,
    itemAvgSalePrice: 112,
    itemInventoryOnHand: inventory,
    itemDaysInStock: 27,
    itemRevenue30d: sold7d * 4 * 112,
    demandSlope24h: demandSlope,
    inventoryPressure,
    cellTimestamp: timestamp,
  }
}

function historicalUser(orderCount: number): OnlineUserFeatures {
  return userFeatures(users[0], new Date('2026-06-04T14:00:00.000Z'), 118, orderCount, 0.64)
}

function historicalItem(views24h: number, sold7d: number): OnlineItemFeatures {
  return itemFeatures(
    'p-trail-jacket',
    new Date('2026-06-04T14:00:00.000Z'),
    views24h,
    sold7d,
    73,
    0.12,
  )
}
