-- BigQuery data foundation for the Retail ML Serving Demo.
-- Replace @PROJECT_ID@, @DATASET@, and @REGION@ before running.

CREATE SCHEMA IF NOT EXISTS `@PROJECT_ID@.@DATASET@`
OPTIONS (
  location = '@BQ_LOCATION@',
  description = 'Retail ML demo offline feature store'
);

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.products` AS
SELECT
  id AS product_id,
  name,
  brand,
  category,
  department,
  sku,
  retail_price,
  cost,
  distribution_center_id AS dc_id
FROM `bigquery-public-data.thelook_ecommerce.products`;

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.users` AS
SELECT * FROM `bigquery-public-data.thelook_ecommerce.users`;

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.orders` AS
SELECT * FROM `bigquery-public-data.thelook_ecommerce.orders`;

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.order_items` AS
SELECT * FROM `bigquery-public-data.thelook_ecommerce.order_items`;

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.events_history` AS
SELECT * FROM `bigquery-public-data.thelook_ecommerce.events`;

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.inventory_items` AS
SELECT * FROM `bigquery-public-data.thelook_ecommerce.inventory_items`;

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.feature_registry` (
  feature_name STRING NOT NULL,
  entity_type STRING NOT NULL,
  source_bq_table STRING NOT NULL,
  bq_field_name STRING NOT NULL,
  bigtable_qualifier STRING NOT NULL,
  data_type STRING NOT NULL,
  freshness_sla_seconds INT64
);

INSERT INTO `@PROJECT_ID@.@DATASET@.feature_registry`
VALUES
  ('item_units_sold_7d', 'item', 'item_features_current', 'item_units_sold_7d',
   'item_units_sold_7d', 'INT64', 120),
  ('item_views_24h', 'item', 'item_features_current', 'item_views_24h',
   'item_views_24h', 'INT64', 120),
  ('item_inventory_on_hand', 'item', 'item_features_current', 'item_inventory_on_hand',
   'item_inventory_on_hand', 'INT64', 120),
  ('demand_slope_24h', 'item', 'item_features_current', 'demand_slope_24h',
   'demand_slope_24h', 'FLOAT64', 120),
  ('user_price_tier', 'user', 'user_features_current', 'user_price_tier',
   'user_price_tier', 'STRING', 900),
  ('coupon_propensity', 'user', 'user_features_current', 'coupon_propensity',
   'coupon_propensity', 'FLOAT64', 900);

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.live_events` (
  product_id STRING NOT NULL,
  event_type STRING NOT NULL,
  user_id STRING,
  occurred_at TIMESTAMP NOT NULL,
  quantity INT64,
  metadata JSON
)
PARTITION BY DATE(occurred_at);
