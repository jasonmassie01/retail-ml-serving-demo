from __future__ import annotations

import json
from datetime import UTC, datetime

from app.config import Settings
from app.models import Candidate, FeatureRow, ServeRequest, VertexScore
from app.serving import RetailServingService


class BigQueryEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        from google.cloud import bigquery

        self.client = bigquery.Client(project=settings.gcp_project)
        self.project = settings.gcp_project
        self.dataset = settings.bq_dataset
        self.model = settings.bq_embedding_model

    def embed_query(self, query: str) -> list[float]:
        from google.cloud import bigquery

        sql = f"""
        SELECT ml_generate_embedding_result AS embedding
        FROM ML.GENERATE_EMBEDDING(
          MODEL `{self.project}.{self.dataset}.{self.model}`,
          (SELECT @query AS content),
          STRUCT(TRUE AS flatten_json_output,
                 'RETRIEVAL_QUERY' AS task_type,
                 1536 AS output_dimensionality)
        )
        WHERE ml_generate_embedding_status = ''
        LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("query", "STRING", query)]
        )
        rows = list(self.client.query(sql, job_config=job_config).result())
        if not rows:
            raise RuntimeError("BigQuery embedding query returned no rows")
        return [float(value) for value in rows[0]["embedding"]]


class AlloyDbCatalog:
    def __init__(self, settings: Settings, embedder: BigQueryEmbeddingClient) -> None:
        from psycopg_pool import ConnectionPool

        password = _resolve_alloydb_password(settings)
        self.embedder = embedder
        self.pool = ConnectionPool(
            conninfo=(
                f"host={settings.alloydb_host} port={settings.alloydb_port} "
                f"dbname={settings.alloydb_database} user={settings.alloydb_user} "
                f"password={password}"
            ),
            open=True,
            min_size=1,
            max_size=4,
        )

    def search(self, request: ServeRequest) -> list[Candidate]:
        embedding = _vector_literal(self.embedder.embed_query(request.query))
        sql = """
        SELECT product_id, name, brand, category, department, retail_price, cost,
               description, image_uri,
               (1.0 - (embedding <=> %s::vector)) AS vector_similarity,
               ts_rank(fts, plainto_tsquery('english', %s)) AS text_rank,
               (((1.0 - (embedding <=> %s::vector)) * 0.7)
                 + (ts_rank(fts, plainto_tsquery('english', %s)) * 0.3)) AS combined_score
        FROM products
        WHERE retail_price <= %s AND category = %s
        ORDER BY combined_score DESC
        LIMIT 100
        """
        params = (
            embedding,
            request.query,
            embedding,
            request.query,
            request.max_price,
            request.category,
        )
        with self.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_candidate_from_row(row) for row in rows]

    def get_product(self, product_id: str) -> Candidate:
        sql = """
        SELECT product_id, name, brand, category, department, retail_price, cost,
               description, image_uri, 0.0, 0.0, 0.0
        FROM products
        WHERE product_id = %s
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (product_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"Unknown product: {product_id}")
        return _candidate_from_row(row)


class BigtableFeatureStore:
    def __init__(self, settings: Settings) -> None:
        from google.cloud import bigtable

        self.column_family = settings.bt_column_family
        client = bigtable.Client(project=settings.gcp_project, admin=True)
        instance = client.instance(settings.bt_instance)
        self.table = instance.table(settings.bt_table, app_profile_id=settings.bt_app_profile)

    def read_rows(self, row_keys: list[str], now: datetime) -> dict[str, FeatureRow]:
        from google.cloud.bigtable.row_set import RowSet

        row_set = RowSet()
        for row_key in row_keys:
            row_set.add_row_key(row_key.encode("utf-8"))
        rows = self.table.read_rows(row_set=row_set)
        rows.consume_all()
        return {
            key.decode("utf-8"): _feature_from_bigtable_row(row, self.column_family)
            for key, row in rows.rows.items()
        }

    def apply_event(self, product_id: str, event_type: str, occurred_at: datetime) -> FeatureRow:
        row_key = f"item#{product_id}"
        current = self.read_rows([row_key], occurred_at).get(row_key)
        values = dict(current.values) if current else {}
        values["item_views_24h"] = int(values.get("item_views_24h", 0)) + 1
        direct_row = self.table.direct_row(row_key.encode("utf-8"))
        for qualifier, value in values.items():
            direct_row.set_cell(self.column_family, qualifier, str(value), timestamp=occurred_at)
        direct_row.commit()
        return FeatureRow(entity_key=row_key, values=values, cell_timestamp=occurred_at)


class VertexEndpointScorer:
    def __init__(self, settings: Settings) -> None:
        from google.cloud import aiplatform

        aiplatform.init(project=settings.gcp_project, location=settings.gcp_region)
        self.endpoints = {
            "recommendations": aiplatform.Endpoint(settings.vertex_ranking_endpoint),
            "search": aiplatform.Endpoint(settings.vertex_ranking_endpoint),
            "pricing": aiplatform.Endpoint(settings.vertex_pricing_endpoint),
        }
        self.coupon_endpoint = aiplatform.Endpoint(settings.vertex_coupon_endpoint)

    def score(
        self,
        use_case: str,
        candidates: list[Candidate],
        features: dict[str, FeatureRow],
    ) -> list[VertexScore]:
        endpoint = self.endpoints[use_case]
        instances = [_instance(candidate, features) for candidate in candidates]
        predictions = endpoint.predict(instances=instances).predictions
        scores = [
            _vertex_score(candidate, prediction)
            for candidate, prediction in zip(candidates, predictions, strict=False)
        ]
        if use_case == "pricing":
            scores = self._add_coupon_scores(scores, instances)
        return scores

    def _add_coupon_scores(
        self,
        scores: list[VertexScore],
        instances: list[dict[str, object]],
    ) -> list[VertexScore]:
        predictions = self.coupon_endpoint.predict(instances=instances).predictions
        return [
            score.model_copy(update={"coupon_tier": _coupon_from_prediction(prediction)})
            for score, prediction in zip(scores, predictions, strict=False)
        ]


class PubSubEventPublisher:
    def __init__(self, settings: Settings) -> None:
        from google.cloud import pubsub_v1

        self.publisher = pubsub_v1.PublisherClient()
        if settings.pubsub_topic.startswith("projects/"):
            self.topic = settings.pubsub_topic
        else:
            self.topic = self.publisher.topic_path(settings.gcp_project, settings.pubsub_topic)

    def publish(self, message: dict[str, str]) -> str:
        payload = json.dumps(message).encode("utf-8")
        future = self.publisher.publish(self.topic, payload, event_type=message["event_type"])
        return str(future.result(timeout=10))


def build_live_service(settings: Settings) -> RetailServingService:
    missing = settings.missing_live_fields()
    if missing:
        raise RuntimeError(f"Missing live settings: {', '.join(missing)}")
    embedder = BigQueryEmbeddingClient(settings)
    return RetailServingService(
        AlloyDbCatalog(settings, embedder),
        BigtableFeatureStore(settings),
        VertexEndpointScorer(settings),
        PubSubEventPublisher(settings),
        service_mode="live",
        freshness_sla_seconds=settings.feature_freshness_sla_seconds,
    )


def _resolve_alloydb_password(settings: Settings) -> str:
    if settings.alloydb_password:
        return settings.alloydb_password
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = (
        f"projects/{settings.gcp_project}/secrets/"
        f"{settings.alloydb_password_secret}/versions/latest"
    )
    return client.access_secret_version(request={"name": name}).payload.data.decode("utf-8")


def _candidate_from_row(row: object) -> Candidate:
    return Candidate(
        product_id=str(row[0]),
        name=str(row[1]),
        brand=str(row[2]),
        category=str(row[3]),
        department=str(row[4]),
        retail_price=float(row[5]),
        cost=float(row[6]),
        description=str(row[7]),
        image_uri=str(row[8] or ""),
        vector_similarity=round(float(row[9]), 3),
        text_rank=round(float(row[10]), 3),
        combined_score=round(float(row[11]), 3),
    )


def _feature_from_bigtable_row(row: object, family: str) -> FeatureRow:
    cells = row.cells.get(family, {})
    values = {}
    timestamps = []
    for qualifier, versions in cells.items():
        latest = versions[0]
        key = qualifier.decode("utf-8") if isinstance(qualifier, bytes) else str(qualifier)
        values[key] = _decode_cell_value(latest.value)
        timestamps.append(latest.timestamp.replace(tzinfo=UTC))
    timestamp = max(timestamps) if timestamps else datetime.now(UTC)
    row_key = row.row_key.decode("utf-8") if isinstance(row.row_key, bytes) else str(row.row_key)
    return FeatureRow(entity_key=row_key, values=values, cell_timestamp=timestamp)


def _decode_cell_value(value: bytes) -> str | int | float | bool | list[str]:
    text = value.decode("utf-8")
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = text
    if isinstance(decoded, str | int | float | bool):
        return decoded
    if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
        return decoded
    return text


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _instance(candidate: Candidate, features: dict[str, FeatureRow]) -> dict[str, object]:
    item = features[f"item#{candidate.product_id}"]
    return {
        "product": candidate.model_dump(mode="json"),
        "item_features": item.model_dump(mode="json"),
    }


def _vertex_score(candidate: Candidate, prediction: object) -> VertexScore:
    if isinstance(prediction, dict):
        return VertexScore(
            product_id=candidate.product_id,
            score=float(prediction.get("score", 0)),
            final_price=_optional_float(prediction.get("final_price")),
        )
    return VertexScore(product_id=candidate.product_id, score=float(prediction))


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _coupon_from_prediction(prediction: object) -> str:
    if isinstance(prediction, dict):
        return str(prediction.get("coupon_tier", "no coupon"))
    return "10% basket coupon" if float(prediction) >= 0.65 else "no coupon"
