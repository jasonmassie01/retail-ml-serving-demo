from datetime import UTC, datetime

from app.models import Candidate, FeatureRow, PriceDecision, ServeRequest, VertexScore
from app.serving import RetailServingService

NOW = datetime(2026, 6, 4, 17, 0, tzinfo=UTC)


class FakeCatalog:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []

    def search(self, request: ServeRequest) -> list[Candidate]:
        self.search_calls.append(
            {
                "use_case": request.use_case,
                "query": request.query,
                "category": request.category,
                "max_price": request.max_price,
            },
        )
        return [
            Candidate(
                product_id="p-trail-jacket",
                name="TrailShield Rain Jacket",
                brand="Cymbal",
                category="Outerwear",
                department="Women",
                retail_price=129.0,
                cost=72.0,
                description="Waterproof shell for rainy commutes.",
                image_uri="gs://retail-demo/products/trail-jacket.png",
                vector_similarity=0.70,
                text_rank=1.0,
                combined_score=0.79,
            ),
            Candidate(
                product_id="p-urban-fleece",
                name="Urban Grid Fleece",
                brand="Cymbal",
                category="Outerwear",
                department="Men",
                retail_price=89.0,
                cost=46.0,
                description="Warm fleece for city walks.",
                image_uri="gs://retail-demo/products/fleece.png",
                vector_similarity=0.91,
                text_rank=0.0,
                combined_score=0.63,
            ),
        ]

    def get_product(self, product_id: str) -> Candidate:
        return next(candidate for candidate in self.search(ServeRequest(product_id=product_id)))


class FakeFeatures:
    def __init__(self) -> None:
        self.read_keys: list[list[str]] = []
        self.events: list[tuple[str, str]] = []

    def read_rows(self, row_keys: list[str], now: datetime) -> dict[str, FeatureRow]:
        self.read_keys.append(row_keys)
        return {
            row_key: FeatureRow(
                entity_key=row_key,
                values=_feature_values(row_key),
                cell_timestamp=now,
            )
            for row_key in row_keys
        }

    def apply_event(self, product_id: str, event_type: str, occurred_at: datetime) -> FeatureRow:
        self.events.append((product_id, event_type))
        return FeatureRow(
            entity_key=f"item#{product_id}",
            values={
                "item_views_24h": 42,
                "item_units_sold_7d": 14,
                "item_inventory_on_hand": 72,
            },
            cell_timestamp=occurred_at,
        )


class FakeScorer:
    def __init__(self, price: float = 120.0) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.price = price

    def score(
        self,
        use_case: str,
        candidates: list[Candidate],
        features: dict[str, FeatureRow],
    ) -> list[VertexScore]:
        self.calls.append((use_case, [candidate.product_id for candidate in candidates]))
        return [
            VertexScore(product_id="p-trail-jacket", score=0.94, final_price=self.price),
            VertexScore(product_id="p-urban-fleece", score=0.73, final_price=85.0),
        ]


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def publish(self, message: dict[str, str]) -> str:
        self.messages.append(message)
        return "projects/p/topics/t/messages/1"


def test_search_pipeline_uses_alloydb_bigtable_and_vertex_in_order() -> None:
    catalog = FakeCatalog()
    features = FakeFeatures()
    scorer = FakeScorer()
    service = RetailServingService(catalog, features, scorer, FakePublisher())

    response = service.serve(
        ServeRequest(
            use_case="search",
            user_id="u-ada",
            query="trail jacket",
            category="Outerwear",
            max_price=160,
            product_id="p-trail-jacket",
        ),
        now=NOW,
    )

    assert catalog.search_calls[0]["query"] == "trail jacket"
    assert features.read_keys == [["user#u-ada", "item#p-trail-jacket", "item#p-urban-fleece"]]
    assert scorer.calls == [("search", ["p-trail-jacket", "p-urban-fleece"])]
    assert [stage.service for stage in response.trace] == [
        "BigQuery",
        "AlloyDB ScaNN",
        "Bigtable",
        "Vertex AI",
    ]
    assert response.results[0].product.product_id == "p-trail-jacket"
    assert response.results[0].retrieval.combined_score == 0.79
    assert response.freshness.rows[0].staleness_seconds == 0


def test_dynamic_pricing_enforces_cost_plus_margin_floor() -> None:
    service = RetailServingService(
        FakeCatalog(),
        FakeFeatures(),
        FakeScorer(price=78.0),
        FakePublisher(),
    )

    response = service.serve(
        ServeRequest(
            use_case="pricing",
            user_id="u-ada",
            product_id="p-trail-jacket",
            category="Outerwear",
        ),
        now=NOW,
    )

    decision = response.results[0].price_decision
    assert isinstance(decision, PriceDecision)
    assert decision.floor_price == 84.96
    assert decision.final_price == 84.96
    assert decision.coupon_tier in {"10% basket coupon", "15% loyalty coupon", "no coupon"}


def test_live_event_publishes_pubsub_and_updates_online_feature_timestamp() -> None:
    features = FakeFeatures()
    publisher = FakePublisher()
    service = RetailServingService(FakeCatalog(), features, FakeScorer(), publisher)

    response = service.publish_event("p-trail-jacket", "product_viewed", NOW)

    assert response.event_id == "projects/p/topics/t/messages/1"
    assert publisher.messages == [
        {
            "product_id": "p-trail-jacket",
            "event_type": "product_viewed",
            "occurred_at": "2026-06-04T17:00:00+00:00",
        },
    ]
    assert features.events == [("p-trail-jacket", "product_viewed")]
    assert response.updated_feature.entity_key == "item#p-trail-jacket"
    assert response.updated_feature.staleness_seconds == 0


def _feature_values(row_key: str) -> dict[str, object]:
    if row_key.startswith("user#"):
        return {
            "user_price_tier": "balanced",
            "coupon_propensity": 0.72,
            "user_category_affinity": ["Outerwear"],
        }

    return {
        "item_views_24h": 38,
        "item_units_sold_7d": 14,
        "item_inventory_on_hand": 73,
        "demand_slope_24h": 0.42,
        "inventory_pressure": 5.2,
    }
