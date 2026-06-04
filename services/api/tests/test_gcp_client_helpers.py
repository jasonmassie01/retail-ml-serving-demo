from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.gcp_clients import (
    AlloyDbCatalog,
    PubSubEventPublisher,
    VertexEndpointScorer,
    _candidate_from_row,
    _coupon_from_prediction,
    _decode_cell_value,
    _feature_from_bigtable_row,
    _instance,
    _resolve_alloydb_password,
    _vector_literal,
    _vertex_score,
    build_live_service,
)
from app.models import Candidate, FeatureRow, ServeRequest, VertexScore


class FakeCell:
    def __init__(self, value: bytes, timestamp: datetime) -> None:
        self.value = value
        self.timestamp = timestamp


class FakeRow:
    def __init__(self) -> None:
        self.row_key = b"item#p-trail-jacket"
        self.cells = {
            "f": {
                b"item_views_24h": [FakeCell(b"42", datetime(2026, 6, 4, 17, 0))],
                b"user_category_affinity": [
                    FakeCell(b'["Outerwear"]', datetime(2026, 6, 4, 17, 1))
                ],
            }
        }


class FakeEmbedder:
    def embed_query(self, query: str) -> list[float]:
        assert query == "trail jacket"
        return [1.0, 0.0]


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.params: tuple[object, ...] | None = None

    def execute(self, sql: str, params: tuple[object, ...]) -> "FakeConnection":
        assert "FROM products" in sql
        self.params = params
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None


class FakePool:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.connection_obj = FakeConnection(rows)

    def connection(self) -> "FakePool":
        return self

    def __enter__(self) -> FakeConnection:
        return self.connection_obj

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakePredictionResponse:
    def __init__(self, predictions: list[object]) -> None:
        self.predictions = predictions


class FakeEndpoint:
    def __init__(self, predictions: list[object]) -> None:
        self.predictions = predictions

    def predict(self, instances: list[dict[str, object]]) -> FakePredictionResponse:
        assert instances
        return FakePredictionResponse(self.predictions)


class FakeFuture:
    def result(self, timeout: int) -> str:
        assert timeout == 10
        return "message-1"


class FakePublisher:
    def __init__(self) -> None:
        self.payload: bytes | None = None
        self.attributes: dict[str, str] | None = None

    def publish(self, topic: str, payload: bytes, **attributes: str) -> FakeFuture:
        assert topic == "projects/p/topics/t"
        self.payload = payload
        self.attributes = attributes
        return FakeFuture()


def test_vector_literal_formats_safe_pgvector_parameter() -> None:
    assert _vector_literal([1, 0.123456789]) == "[1.00000000,0.12345679]"


def test_candidate_from_alloydb_row_preserves_scores() -> None:
    candidate = _candidate_from_row(
        (
            123,
            "TrailShield Rain Jacket",
            "Cymbal",
            "Outerwear",
            "Women",
            129,
            72,
            "Waterproof shell.",
            "gs://bucket/product.png",
            0.7654,
            0.5,
            0.6251,
        )
    )

    assert candidate.product_id == "123"
    assert candidate.retail_price == 129
    assert candidate.vector_similarity == 0.765
    assert candidate.combined_score == 0.625


def test_bigtable_cell_decoding_handles_json_numbers_arrays_and_text() -> None:
    assert _decode_cell_value(b"42") == 42
    assert _decode_cell_value(b"0.72") == 0.72
    assert _decode_cell_value(b'["Outerwear"]') == ["Outerwear"]
    assert _decode_cell_value(b"not-json") == "not-json"


def test_feature_from_bigtable_row_uses_latest_cell_timestamp() -> None:
    feature = _feature_from_bigtable_row(FakeRow(), "f")

    assert feature.entity_key == "item#p-trail-jacket"
    assert feature.values["item_views_24h"] == 42
    assert feature.values["user_category_affinity"] == ["Outerwear"]
    assert feature.cell_timestamp == datetime(2026, 6, 4, 17, 1, tzinfo=UTC)


def test_vertex_score_and_coupon_prediction_shapes() -> None:
    candidate = _candidate()

    score = _vertex_score(candidate, {"score": "0.91", "final_price": "118.5"})

    assert score.product_id == "p-trail-jacket"
    assert score.score == 0.91
    assert score.final_price == 118.5
    assert _coupon_from_prediction({"coupon_tier": "15% loyalty coupon"}) == "15% loyalty coupon"
    assert _coupon_from_prediction(0.7) == "10% basket coupon"
    assert _coupon_from_prediction(0.2) == "no coupon"


def test_vertex_instance_contains_product_and_item_features() -> None:
    candidate = _candidate()
    feature = FeatureRow(
        entity_key="item#p-trail-jacket",
        values={"item_views_24h": 42},
        cell_timestamp=datetime(2026, 6, 4, 17, 0, tzinfo=UTC),
    )

    instance = _instance(candidate, {"item#p-trail-jacket": feature})

    assert instance["product"]["product_id"] == "p-trail-jacket"
    assert instance["item_features"]["values"]["item_views_24h"] == 42


def test_alloydb_search_uses_embedding_and_parameterized_filters() -> None:
    row = _catalog_row()
    catalog = AlloyDbCatalog.__new__(AlloyDbCatalog)
    catalog.embedder = FakeEmbedder()
    catalog.pool = FakePool([row])

    results = catalog.search(
        ServeRequest(
            use_case="search",
            query="trail jacket",
            category="Outerwear",
            max_price=160,
        )
    )

    assert results[0].product_id == "123"
    assert catalog.pool.connection_obj.params == (
        "[1.00000000,0.00000000]",
        "trail jacket",
        "[1.00000000,0.00000000]",
        "trail jacket",
        160,
        "Outerwear",
    )


def test_alloydb_get_product_raises_for_missing_row() -> None:
    catalog = AlloyDbCatalog.__new__(AlloyDbCatalog)
    catalog.pool = FakePool([])

    with pytest.raises(RuntimeError, match="Unknown product"):
        catalog.get_product("missing")


def test_coupon_endpoint_predictions_are_merged_into_pricing_scores() -> None:
    scorer = VertexEndpointScorer.__new__(VertexEndpointScorer)
    scorer.coupon_endpoint = FakeEndpoint([{"coupon_tier": "15% loyalty coupon"}])

    scores = scorer._add_coupon_scores(
        [VertexScore(product_id="p-trail-jacket", score=0.9)],
        [{"product": {"product_id": "p-trail-jacket"}}],
    )

    assert scores[0].coupon_tier == "15% loyalty coupon"


def test_pubsub_publisher_serializes_event_payload_and_attributes() -> None:
    publisher = PubSubEventPublisher.__new__(PubSubEventPublisher)
    publisher.publisher = FakePublisher()
    publisher.topic = "projects/p/topics/t"

    message_id = publisher.publish({"event_type": "product_viewed", "product_id": "p1"})

    assert message_id == "message-1"
    assert b'"product_id": "p1"' in publisher.publisher.payload
    assert publisher.publisher.attributes == {"event_type": "product_viewed"}


def test_live_builder_fails_fast_when_required_settings_are_missing() -> None:
    with pytest.raises(RuntimeError, match="Missing live settings"):
        build_live_service(Settings(serving_mode="live"))


def test_alloydb_password_prefers_direct_env_value() -> None:
    password = _resolve_alloydb_password(
        Settings(serving_mode="live", alloydb_password="direct-password")
    )

    assert password == "direct-password"


def _candidate() -> Candidate:
    return Candidate(
        product_id="p-trail-jacket",
        name="TrailShield Rain Jacket",
        brand="Cymbal",
        category="Outerwear",
        department="Women",
        retail_price=129,
        cost=72,
        description="Waterproof shell.",
    )


def _catalog_row() -> tuple[object, ...]:
    return (
        123,
        "TrailShield Rain Jacket",
        "Cymbal",
        "Outerwear",
        "Women",
        129,
        72,
        "Waterproof shell.",
        "gs://bucket/product.png",
        0.7654,
        0.5,
        0.6251,
    )
