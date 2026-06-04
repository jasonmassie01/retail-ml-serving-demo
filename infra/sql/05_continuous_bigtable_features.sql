-- Continuous-query dynamic feature demo. Run with:
-- bq query --continuous=true --connection_property=service_account=SA_EMAIL ...
-- Requires Enterprise or Enterprise Plus BigQuery reservation with CONTINUOUS jobs.

EXPORT DATA OPTIONS (
  uri = '@BT_URI@',
  format = 'CLOUD_BIGTABLE',
  overwrite = TRUE,
  truncate = TRUE,
  bigtable_options = '''{
    "columnFamilies": [{
      "familyId": "f",
      "encoding": "TEXT",
      "columns": [
        {"qualifierString": "item_views_24h", "fieldName": "item_views_24h"},
        {"qualifierString": "demand_slope_24h", "fieldName": "demand_slope_24h"}
      ]
    }]
  }'''
) AS (
  SELECT
    CONCAT('item#', product_id) AS rowkey,
    _CHANGE_TIMESTAMP,
    COUNTIF(event_type = 'product_viewed') OVER (
      PARTITION BY product_id
      ORDER BY occurred_at
      RANGE BETWEEN INTERVAL 24 HOUR PRECEDING AND CURRENT ROW
    ) AS item_views_24h,
    SAFE_DIVIDE(
      COUNTIF(event_type = 'product_viewed') OVER (
        PARTITION BY product_id
        ORDER BY occurred_at
        RANGE BETWEEN INTERVAL 1 HOUR PRECEDING AND CURRENT ROW
      ),
      60
    ) AS demand_slope_24h
  FROM APPENDS(
    TABLE `@PROJECT_ID@.@DATASET@.live_events`,
    CURRENT_TIMESTAMP() - INTERVAL 10 MINUTE
  )
  WHERE event_type IN ('product_viewed', 'item_purchased')
);
