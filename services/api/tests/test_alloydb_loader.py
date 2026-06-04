import pytest

from app import alloydb_loader
from app.alloydb_loader import LoadConfig, build_product_source_query, load_catalog


class FakeQueryJob:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.page_size = 0

    def result(self, page_size: int) -> list[dict[str, object]]:
        self.page_size = page_size
        return self.rows


class FakeBigQueryClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.sql = ""
        self.job: FakeQueryJob | None = None

    def query(self, sql: str) -> FakeQueryJob:
        self.sql = sql
        self.job = FakeQueryJob(self.rows)
        return self.job


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.batches: list[list[tuple[object, ...]]] = []
        self.commits = 0

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def executemany(self, sql: str, params: list[tuple[object, ...]]) -> None:
        self.executed.append(sql)
        self.batches.append(params)

    def commit(self) -> None:
        self.commits += 1


def test_product_source_query_reads_enriched_thelook_artifacts() -> None:
    sql = build_product_source_query("demo-project", "retail_demo")

    assert "`demo-project.retail_demo.product_content`" in sql
    assert "`demo-project.retail_demo.product_embeddings_normalized`" in sql
    assert "ARRAY_LENGTH(e.embedding) = 1536" in sql
    assert "JOIN" in sql


def test_load_catalog_bootstraps_schema_and_upserts_embeddings() -> None:
    bq = FakeBigQueryClient([_row(1), _row(2), _row(3)])
    conn = FakeConnection()

    stats = load_catalog(
        bq,
        conn,
        LoadConfig(project_id="demo-project", dataset_id="retail_demo", batch_size=2),
    )

    assert stats.products_loaded == 3
    assert stats.batches_written == 2
    assert bq.job is not None
    assert bq.job.page_size == 2
    assert conn.commits == 1
    assert any("CREATE EXTENSION IF NOT EXISTS alloydb_scann" in sql for sql in conn.executed)
    assert any(
        "CREATE INDEX IF NOT EXISTS products_embedding_scann" in sql for sql in conn.executed
    )
    assert "product_content" in bq.sql
    assert conn.batches[0][0] == (
        1,
        "Trail Jacket 1",
        "Cymbal",
        "Outerwear",
        "Women",
        "SKU-1",
        129.0,
        72.0,
        4,
        "Generated description 1",
        "",
        "Content text 1",
        "[0.10000000,0.20000000,0.30000000]",
    )


def test_load_catalog_rejects_empty_embedding_before_writing() -> None:
    bq = FakeBigQueryClient([_row(1, embedding=[])])
    conn = FakeConnection()

    try:
        load_catalog(
            bq,
            conn,
            LoadConfig(project_id="demo-project", dataset_id="retail_demo", batch_size=2),
        )
    except ValueError as exc:
        assert "embedding" in str(exc)
    else:
        raise AssertionError("Expected empty embedding to fail")

    assert conn.batches == []
    assert conn.commits == 0


def test_build_product_source_query_rejects_invalid_identifiers() -> None:
    with pytest.raises(ValueError, match="Invalid BigQuery identifier"):
        build_product_source_query("demo-project", "retail.demo")


def test_load_catalog_rejects_invalid_batch_size_before_querying() -> None:
    bq = FakeBigQueryClient([_row(1)])
    conn = FakeConnection()

    with pytest.raises(ValueError, match="batch_size"):
        load_catalog(bq, conn, LoadConfig("demo-project", "retail_demo", batch_size=0))

    assert bq.sql == ""
    assert conn.executed == []


def test_load_catalog_accepts_attribute_style_bigquery_rows() -> None:
    bq = FakeBigQueryClient([AttributeRow(_row(1))])
    conn = FakeConnection()

    stats = load_catalog(bq, conn, LoadConfig("demo-project", "retail_demo", batch_size=1))

    assert stats.products_loaded == 1
    assert conn.batches[0][0][0] == 1


def test_parse_args_reads_required_loader_settings() -> None:
    args = alloydb_loader._parse_args(
        [
            "--project-id",
            "demo-project",
            "--alloydb-host",
            "10.0.0.5",
            "--alloydb-database",
            "retail",
            "--alloydb-user",
            "retail_app",
            "--batch-size",
            "25",
        ]
    )

    assert args.project_id == "demo-project"
    assert args.alloydb_host == "10.0.0.5"
    assert args.batch_size == 25


def test_parse_args_fails_fast_when_required_settings_are_missing() -> None:
    with pytest.raises(RuntimeError, match="project_id"):
        alloydb_loader._parse_args(["--alloydb-host", "10.0.0.5"])


def test_resolve_password_prefers_direct_value_without_secret_lookup() -> None:
    password = alloydb_loader._resolve_password("demo-project", "direct-password", "")

    assert password == "direct-password"


class AttributeRow:
    def __init__(self, values: dict[str, object]) -> None:
        self.__dict__.update(values)


def _row(product_id: int, embedding: list[float] | None = None) -> dict[str, object]:
    row_embedding = [0.1, 0.2, 0.3] if embedding is None else embedding
    return {
        "product_id": product_id,
        "name": f"Trail Jacket {product_id}",
        "brand": "Cymbal",
        "category": "Outerwear",
        "department": "Women",
        "sku": f"SKU-{product_id}",
        "retail_price": 129.0,
        "cost": 72.0,
        "dc_id": 4,
        "generated_description": f"Generated description {product_id}",
        "image_uri": None,
        "content": f"Content text {product_id}",
        "embedding": row_embedding,
    }
