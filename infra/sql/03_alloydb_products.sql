-- Run in AlloyDB after loading product_content plus normalized embeddings.

CREATE EXTENSION IF NOT EXISTS alloydb_scann CASCADE;

CREATE TABLE IF NOT EXISTS products (
  product_id BIGINT PRIMARY KEY,
  name TEXT,
  brand TEXT,
  category TEXT,
  department TEXT,
  sku TEXT,
  retail_price NUMERIC,
  cost NUMERIC,
  dc_id INT,
  description TEXT,
  image_uri TEXT,
  content_text TEXT,
  embedding vector(1536),
  fts tsvector GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, ''))
  ) STORED
);

CREATE INDEX IF NOT EXISTS products_fts_gin ON products USING gin (fts);
CREATE INDEX IF NOT EXISTS products_cat_price ON products (category, retail_price);

-- Build this only after embeddings are loaded. ScaNN indexes can be sensitive to
-- empty or tiny tables, so the load script runs this as a separate step.
CREATE INDEX IF NOT EXISTS products_embedding_scann
  ON products USING scann (embedding cosine)
  WITH (num_leaves = 500, max_num_levels = 2);

-- Hybrid retrieval template used by the serving API.
SELECT product_id, name, retail_price,
  (1.0 - (embedding <=> $1::vector)) AS vector_similarity,
  ts_rank(fts, plainto_tsquery('english', $2)) AS text_rank,
  (((1.0 - (embedding <=> $1::vector)) * 0.7)
    + (ts_rank(fts, plainto_tsquery('english', $2)) * 0.3)) AS combined_score
FROM products
WHERE retail_price <= $3 AND category = $4
ORDER BY combined_score DESC
LIMIT 100;
