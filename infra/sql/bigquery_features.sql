-- Reference only. Not executed by the local demo.
-- BigQuery feature registry and embedding generation examples.

CREATE TABLE retail_demo.feature_registry (
  feature_name STRING NOT NULL,
  entity_type STRING NOT NULL,
  source_bq_table STRING NOT NULL,
  bq_field_name STRING NOT NULL,
  bigtable_qualifier STRING NOT NULL,
  data_type STRING NOT NULL,
  freshness_sla_seconds INT64
);

CREATE OR REPLACE MODEL `retail_demo.gemini_embed`
REMOTE WITH CONNECTION `PROJECT.REGION.vertex_conn`
OPTIONS (ENDPOINT = 'gemini-embedding-001');

CREATE OR REPLACE TABLE `retail_demo.product_embeddings` AS
SELECT
  product_id,
  ml_generate_embedding_result AS embedding_raw
FROM ML.GENERATE_EMBEDDING(
  MODEL `retail_demo.gemini_embed`,
  (SELECT product_id, content FROM `retail_demo.product_content`),
  STRUCT(1536 AS output_dimensionality, 'RETRIEVAL_DOCUMENT' AS task_type)
);

CREATE OR REPLACE TABLE `retail_demo.product_embeddings_normalized` AS
SELECT product_id,
  ARRAY(
    SELECT e / SQRT((SELECT SUM(x * x) FROM UNNEST(embedding_raw) x))
    FROM UNNEST(embedding_raw) e
  ) AS embedding
FROM `retail_demo.product_embeddings`;
