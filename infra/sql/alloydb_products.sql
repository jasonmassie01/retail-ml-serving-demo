-- Reference only. Not executed by the local demo.
-- AlloyDB catalog and hybrid retrieval surface from the source spec.

CREATE TABLE products (
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

CREATE INDEX products_embedding_scann
  ON products USING scann (embedding cosine)
  WITH (num_leaves = 500, max_num_levels = 2);

CREATE INDEX products_fts_gin ON products USING gin (fts);
CREATE INDEX products_cat_price ON products (category, retail_price);

-- Blend vector and text rank before limiting to avoid dropping keyword matches.
SELECT product_id, name, retail_price,
  (1.0 - (embedding <=> $1)) AS vector_similarity,
  ts_rank(fts, plainto_tsquery('english', $2)) AS text_rank,
  (((1.0 - (embedding <=> $1)) * 0.7)
    + (ts_rank(fts, plainto_tsquery('english', $2)) * 0.3)) AS combined_score
FROM products
WHERE retail_price < $3 AND category = $4
ORDER BY combined_score DESC
LIMIT 100;
