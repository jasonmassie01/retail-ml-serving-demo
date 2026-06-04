-- Scheduled BigQuery to Bigtable reverse ETL. This is the cheap v1 sync path.

EXPORT DATA OPTIONS (
  uri = '@BT_URI@',
  format = 'CLOUD_BIGTABLE',
  overwrite = TRUE,
  bigtable_options = '''{
    "columnFamilies": [{
      "familyId": "f",
      "encoding": "TEXT",
      "columns": [
        {"qualifierString": "item_units_sold_7d", "fieldName": "item_units_sold_7d"},
        {"qualifierString": "item_units_sold_30d", "fieldName": "item_units_sold_30d"},
        {"qualifierString": "item_views_24h", "fieldName": "item_views_24h"},
        {"qualifierString": "item_inventory_on_hand", "fieldName": "item_inventory_on_hand"},
        {"qualifierString": "demand_slope_24h", "fieldName": "demand_slope_24h"},
        {"qualifierString": "inventory_pressure", "fieldName": "inventory_pressure"}
      ]
    }]
  }'''
) AS
SELECT
  CONCAT('item#', CAST(product_id AS STRING)) AS rowkey,
  feature_computed_at AS _CHANGE_TIMESTAMP,
  item_units_sold_7d,
  item_units_sold_30d,
  item_views_24h,
  item_inventory_on_hand,
  demand_slope_24h,
  inventory_pressure
FROM `@PROJECT_ID@.@DATASET@.item_features_current`;
