-- Point-in-time training example extraction. The upper bound is the label event
-- timestamp; later feature values cannot leak into the training row.

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.ranking_training_examples` AS
WITH label_events AS (
  SELECT
    user_id,
    SAFE_CAST(REGEXP_EXTRACT(uri, r'/product/([0-9]+)') AS INT64) AS product_id,
    created_at AS label_event_at,
    IF(event_type = 'purchase', 1, 0) AS label
  FROM `@PROJECT_ID@.@DATASET@.events_history`
  WHERE event_type IN ('product', 'purchase')
),
item_history AS (
  SELECT *
  FROM `@PROJECT_ID@.@DATASET@.item_features_current`
),
user_history AS (
  SELECT *
  FROM `@PROJECT_ID@.@DATASET@.user_features_current`
)
SELECT
  labels.user_id,
  labels.product_id,
  labels.label_event_at,
  labels.label,
  users.user_aov_30d,
  users.user_order_count_90d,
  users.user_price_tier,
  items.item_units_sold_7d,
  items.item_views_24h,
  items.item_inventory_on_hand
FROM label_events labels
JOIN user_history users
  ON users.user_id = labels.user_id
  AND users.feature_computed_at <= labels.label_event_at
JOIN item_history items
  ON items.product_id = labels.product_id
  AND items.feature_computed_at <= labels.label_event_at;
