from __future__ import annotations

import argparse
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

DDL_BEFORE_LOAD = """
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
"""

DDL_AFTER_LOAD = """
CREATE INDEX IF NOT EXISTS products_fts_gin ON products USING gin (fts);
CREATE INDEX IF NOT EXISTS products_cat_price ON products (category, retail_price);
CREATE INDEX IF NOT EXISTS products_embedding_scann
  ON products USING scann (embedding cosine)
  WITH (num_leaves = 500, max_num_levels = 2);
"""

UPSERT_PRODUCT_SQL = """
INSERT INTO products (
  product_id, name, brand, category, department, sku, retail_price, cost, dc_id,
  description, image_uri, content_text, embedding
) VALUES (
  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector
)
ON CONFLICT (product_id) DO UPDATE SET
  name = EXCLUDED.name,
  brand = EXCLUDED.brand,
  category = EXCLUDED.category,
  department = EXCLUDED.department,
  sku = EXCLUDED.sku,
  retail_price = EXCLUDED.retail_price,
  cost = EXCLUDED.cost,
  dc_id = EXCLUDED.dc_id,
  description = EXCLUDED.description,
  image_uri = EXCLUDED.image_uri,
  content_text = EXCLUDED.content_text,
  embedding = EXCLUDED.embedding;
"""


@dataclass(frozen=True)
class LoadConfig:
    project_id: str
    dataset_id: str
    batch_size: int = 500


@dataclass(frozen=True)
class LoadStats:
    products_loaded: int
    batches_written: int


def build_product_source_query(project_id: str, dataset_id: str) -> str:
    project = _validated_identifier(project_id, allow_dash=True)
    dataset = _validated_identifier(dataset_id, allow_dash=False)
    return f"""
    SELECT
      c.product_id,
      c.name,
      c.brand,
      c.category,
      c.department,
      c.sku,
      c.retail_price,
      c.cost,
      c.dc_id,
      c.generated_description,
      c.image_uri,
      c.content,
      e.embedding
    FROM `{project}.{dataset}.product_content` c
    JOIN `{project}.{dataset}.product_embeddings_normalized` e USING (product_id)
    WHERE ARRAY_LENGTH(e.embedding) = 1536
    ORDER BY c.product_id
    """


def load_catalog(bq_client: object, conn: object, config: LoadConfig) -> LoadStats:
    if config.batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    rows = bq_client.query(
        build_product_source_query(config.project_id, config.dataset_id)
    ).result(page_size=config.batch_size)
    conn.execute(DDL_BEFORE_LOAD)
    products_loaded = 0
    batches_written = 0
    batch: list[tuple[object, ...]] = []

    for row in rows:
        batch.append(_product_params(row))
        products_loaded += 1
        if len(batch) == config.batch_size:
            _write_batch(conn, batch)
            batches_written += 1
            batch = []

    if batch:
        _write_batch(conn, batch)
        batches_written += 1

    conn.execute(DDL_AFTER_LOAD)
    conn.commit()
    return LoadStats(products_loaded=products_loaded, batches_written=batches_written)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    password = _resolve_password(args.project_id, args.alloydb_password, args.password_secret)
    stats = _run_live_load(args, password)
    print(
        f"Loaded {stats.products_loaded} products into AlloyDB "
        f"in {stats.batches_written} batches"
    )


def _run_live_load(args: argparse.Namespace, password: str) -> LoadStats:
    import psycopg
    from google.cloud import bigquery

    conninfo = (
        f"host={args.alloydb_host} port={args.alloydb_port} "
        f"dbname={args.alloydb_database} user={args.alloydb_user} password={password}"
    )
    config = LoadConfig(args.project_id, args.dataset, args.batch_size)
    with psycopg.connect(conninfo) as conn:
        return load_catalog(bigquery.Client(project=args.project_id), conn, config)


def _product_params(row: object) -> tuple[object, ...]:
    return (
        int(_field(row, "product_id")),
        _text(row, "name"),
        _text(row, "brand"),
        _text(row, "category"),
        _text(row, "department"),
        _text(row, "sku"),
        float(_field(row, "retail_price")),
        float(_field(row, "cost")),
        int(_field(row, "dc_id")),
        _text(row, "generated_description"),
        _optional_text(row, "image_uri"),
        _text(row, "content"),
        _embedding_literal(_field(row, "embedding")),
    )


def _write_batch(conn: object, batch: list[tuple[object, ...]]) -> None:
    conn.executemany(UPSERT_PRODUCT_SQL, batch)


def _embedding_literal(value: object) -> str:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence) or not value:
        raise ValueError("embedding must be a non-empty numeric sequence")
    try:
        return "[" + ",".join(f"{float(item):.8f}" for item in value) + "]"
    except (TypeError, ValueError) as exc:
        raise ValueError("embedding must contain only numeric values") from exc


def _field(row: object, name: str) -> object:
    if isinstance(row, Mapping):
        return row[name]
    try:
        return row[name]  # type: ignore[index]
    except (KeyError, TypeError):
        return getattr(row, name)


def _text(row: object, name: str) -> str:
    value = _field(row, name)
    if value is None:
        raise ValueError(f"{name} cannot be null")
    return str(value)


def _optional_text(row: object, name: str) -> str:
    value = _field(row, name)
    return "" if value is None else str(value)


def _resolve_password(project_id: str, password: str, secret_name: str) -> str:
    if password:
        return password
    if not secret_name:
        raise RuntimeError("Provide ALLOYDB_PASSWORD or ALLOYDB_PASSWORD_SECRET")

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    return client.access_secret_version(request={"name": name}).payload.data.decode("utf-8")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load enriched BigQuery catalog into AlloyDB")
    parser.add_argument("--project-id", default=os.getenv("GCP_PROJECT", ""))
    parser.add_argument("--dataset", default=os.getenv("BQ_DATASET", "retail_demo"))
    parser.add_argument("--alloydb-host", default=os.getenv("ALLOYDB_HOST", ""))
    parser.add_argument("--alloydb-port", type=int, default=int(os.getenv("ALLOYDB_PORT", "5432")))
    parser.add_argument("--alloydb-database", default=os.getenv("ALLOYDB_DATABASE", "retail"))
    parser.add_argument("--alloydb-user", default=os.getenv("ALLOYDB_USER", "retail_app"))
    parser.add_argument("--alloydb-password", default=os.getenv("ALLOYDB_PASSWORD", ""))
    parser.add_argument("--password-secret", default=os.getenv("ALLOYDB_PASSWORD_SECRET", ""))
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("ALLOYDB_LOAD_BATCH_SIZE", "500")),
    )
    args = parser.parse_args(argv)
    _require_args(args, ["project_id", "alloydb_host", "alloydb_database", "alloydb_user"])
    return args


def _require_args(args: argparse.Namespace, names: Sequence[str]) -> None:
    missing = [name for name in names if not getattr(args, name)]
    if missing:
        raise RuntimeError(f"Missing required loader settings: {', '.join(missing)}")


def _validated_identifier(value: str, allow_dash: bool) -> str:
    pattern = r"[A-Za-z0-9_-]+" if allow_dash else r"[A-Za-z0-9_]+"
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid BigQuery identifier: {value}")
    return value


if __name__ == "__main__":
    main()
