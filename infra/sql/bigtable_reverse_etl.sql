-- Reference only. Not executed by the local demo.
-- Scheduled BigQuery -> Bigtable reverse ETL shape from the source spec.

EXPORT DATA OPTIONS (
  uri = 'https://bigtable.googleapis.com/projects/PROJECT/instances/INSTANCE/tables/TABLE',
  format = 'CLOUD_BIGTABLE',
  bigtable_options = '''{
    "columnFamilies": [{
      "familyId": "f",
      "encoding": "BINARY",
      "columns": [
        {"qualifierString": "item_units_sold_7d", "fieldName": "item_units_sold_7d"},
        {"qualifierString": "item_views_24h", "fieldName": "item_views_24h"},
        {"qualifierString": "item_inventory_on_hand", "fieldName": "item_inventory_on_hand"}
      ]
    }]
  }'''
) AS
SELECT
  CONCAT('item#', CAST(product_id AS STRING)) AS rowkey,
  item_units_sold_7d,
  item_views_24h,
  item_inventory_on_hand
FROM `retail_demo.item_features_current`;
