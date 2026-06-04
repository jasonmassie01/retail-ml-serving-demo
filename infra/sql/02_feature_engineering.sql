-- Offline features. These definitions are the single source used for online sync
-- and for point-in-time training extraction.

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.item_features_current` AS
WITH item_sales AS (
  SELECT
    product_id,
    COUNTIF(created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY))
      AS item_units_sold_7d,
    COUNTIF(created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY))
      AS item_units_sold_30d,
    AVG(IF(created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY), sale_price, NULL))
      AS item_avg_sale_price,
    SUM(IF(created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY), sale_price, 0))
      AS item_revenue_30d,
    SAFE_DIVIDE(COUNTIF(status = 'Returned'), COUNT(*)) AS item_return_rate
  FROM `@PROJECT_ID@.@DATASET@.order_items`
  GROUP BY product_id
),
item_views AS (
  SELECT
    SAFE_CAST(REGEXP_EXTRACT(uri, r'/product/([0-9]+)') AS INT64) AS product_id,
    COUNTIF(created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR))
      AS item_views_24h,
    COUNTIF(created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY))
      AS item_views_30d
  FROM `@PROJECT_ID@.@DATASET@.events_history`
  WHERE event_type = 'product'
  GROUP BY product_id
),
inventory AS (
  SELECT
    product_id,
    COUNTIF(sold_at IS NULL) AS item_inventory_on_hand,
    TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MIN(created_at), DAY) AS item_days_in_stock
  FROM `@PROJECT_ID@.@DATASET@.inventory_items`
  WHERE sold_at IS NULL
  GROUP BY product_id
)
SELECT
  p.product_id,
  CURRENT_TIMESTAMP() AS feature_computed_at,
  COALESCE(s.item_units_sold_7d, 0) AS item_units_sold_7d,
  COALESCE(s.item_units_sold_30d, 0) AS item_units_sold_30d,
  COALESCE(v.item_views_24h, 0) AS item_views_24h,
  SAFE_DIVIDE(COALESCE(s.item_units_sold_30d, 0), NULLIF(v.item_views_30d, 0))
    AS item_view_to_purchase_rate,
  COALESCE(s.item_return_rate, 0) AS item_return_rate,
  COALESCE(s.item_avg_sale_price, p.retail_price) AS item_avg_sale_price,
  COALESCE(i.item_inventory_on_hand, 0) AS item_inventory_on_hand,
  COALESCE(i.item_days_in_stock, 0) AS item_days_in_stock,
  COALESCE(s.item_revenue_30d, 0) AS item_revenue_30d,
  SAFE_DIVIDE(COALESCE(v.item_views_24h, 0), 24) AS demand_slope_24h,
  SAFE_DIVIDE(COALESCE(i.item_inventory_on_hand, 0), NULLIF(s.item_units_sold_7d, 0))
    AS inventory_pressure
FROM `@PROJECT_ID@.@DATASET@.products` p
LEFT JOIN item_sales s USING (product_id)
LEFT JOIN item_views v USING (product_id)
LEFT JOIN inventory i USING (product_id);

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.user_features_current` AS
WITH user_orders AS (
  SELECT
    o.user_id,
    AVG(IF(oi.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY),
      oi.sale_price, NULL)) AS user_aov_30d,
    COUNT(DISTINCT IF(o.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY),
      o.order_id, NULL)) AS user_order_count_90d,
    SAFE_DIVIDE(COUNTIF(oi.status = 'Returned'), COUNT(*)) AS user_return_rate,
    TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(o.created_at), DAY) AS user_days_since_last_order
  FROM `@PROJECT_ID@.@DATASET@.orders` o
  JOIN `@PROJECT_ID@.@DATASET@.order_items` oi USING (order_id)
  GROUP BY o.user_id
),
sessions AS (
  SELECT
    user_id,
    COUNT(DISTINCT session_id) AS user_sessions_7d
  FROM `@PROJECT_ID@.@DATASET@.events_history`
  WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY user_id
),
affinity AS (
  SELECT
    oi.user_id,
    ARRAY_AGG(p.category ORDER BY COUNT(*) DESC LIMIT 5) AS user_category_affinity
  FROM `@PROJECT_ID@.@DATASET@.order_items` oi
  JOIN `@PROJECT_ID@.@DATASET@.products` p USING (product_id)
  GROUP BY oi.user_id
)
SELECT
  u.id AS user_id,
  CURRENT_TIMESTAMP() AS feature_computed_at,
  COALESCE(o.user_aov_30d, 0) AS user_aov_30d,
  COALESCE(o.user_order_count_90d, 0) AS user_order_count_90d,
  COALESCE(o.user_return_rate, 0) AS user_return_rate,
  COALESCE(s.user_sessions_7d, 0) AS user_sessions_7d,
  COALESCE(o.user_days_since_last_order, 365) AS user_days_since_last_order,
  COALESCE(a.user_category_affinity, []) AS user_category_affinity,
  CASE
    WHEN COALESCE(o.user_aov_30d, 0) < 60 THEN 'value'
    WHEN COALESCE(o.user_aov_30d, 0) > 140 THEN 'premium'
    ELSE 'balanced'
  END AS user_price_tier,
  LEAST(0.95, GREATEST(0.05, 1 - SAFE_DIVIDE(COALESCE(o.user_aov_30d, 0), 250)))
    AS coupon_propensity
FROM `@PROJECT_ID@.@DATASET@.users` u
LEFT JOIN user_orders o ON u.id = o.user_id
LEFT JOIN sessions s ON u.id = s.user_id
LEFT JOIN affinity a ON u.id = a.user_id;
