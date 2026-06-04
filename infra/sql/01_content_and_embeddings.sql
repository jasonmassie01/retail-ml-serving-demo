-- Catalog enrichment and embedding generation.
-- The generated description is deterministic here; swap the description expression
-- for AI.GENERATE/ML.GENERATE_TEXT when you enable text enrichment billing.

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.product_content` AS
SELECT
  product_id,
  name,
  brand,
  category,
  department,
  sku,
  retail_price,
  cost,
  dc_id,
  CONCAT(
    name,
    ' by ',
    brand,
    ' is a ',
    category,
    ' product for the ',
    department,
    ' department.'
  ) AS generated_description,
  CONCAT(
    name,
    '. Brand: ',
    brand,
    '. Category: ',
    department,
    ' / ',
    category,
    '. ',
    name,
    ' by ',
    brand,
    '.'
  ) AS content,
  CAST(NULL AS STRING) AS image_uri
FROM `@PROJECT_ID@.@DATASET@.products`;

CREATE OR REPLACE MODEL `@PROJECT_ID@.@DATASET@.gemini_embed`
REMOTE WITH CONNECTION `@PROJECT_ID@.@BQ_LOCATION@.@BQ_CONNECTION_ID@`
OPTIONS (ENDPOINT = 'gemini-embedding-001');

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.product_embeddings_raw` AS
SELECT
  product_id,
  ml_generate_embedding_result AS embedding_raw,
  ml_generate_embedding_statistics AS embedding_statistics,
  ml_generate_embedding_status AS embedding_status
FROM ML.GENERATE_EMBEDDING(
  MODEL `@PROJECT_ID@.@DATASET@.gemini_embed`,
  (
    SELECT
      product_id,
      name AS title,
      content
    FROM `@PROJECT_ID@.@DATASET@.product_content`
  ),
  STRUCT(
    TRUE AS flatten_json_output,
    'RETRIEVAL_DOCUMENT' AS task_type,
    1536 AS output_dimensionality
  )
);

CREATE OR REPLACE TABLE `@PROJECT_ID@.@DATASET@.product_embeddings_normalized` AS
WITH norms AS (
  SELECT
    product_id,
    embedding_raw,
    SQRT((SELECT SUM(value * value) FROM UNNEST(embedding_raw) value)) AS l2_norm
  FROM `@PROJECT_ID@.@DATASET@.product_embeddings_raw`
  WHERE embedding_status = ''
)
SELECT
  product_id,
  ARRAY(
    SELECT value / NULLIF(l2_norm, 0)
    FROM UNNEST(embedding_raw) value
  ) AS embedding
FROM norms;
