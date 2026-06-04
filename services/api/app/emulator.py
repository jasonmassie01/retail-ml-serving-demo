from __future__ import annotations

from datetime import UTC, datetime

from app.config import Settings
from app.models import Candidate, FeatureRow, ServeRequest, VertexScore
from app.serving import RetailServingService

CATALOG = [
    Candidate(
        product_id="p-trail-jacket",
        name="TrailShield Rain Jacket",
        brand="Cymbal",
        category="Outerwear",
        department="Women",
        retail_price=129.0,
        cost=72.0,
        description="Waterproof shell with sealed seams for rainy commutes.",
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
        description="Lightweight grid fleece for layering and city walks.",
        image_uri="gs://retail-demo/products/urban-fleece.png",
        vector_similarity=0.91,
        text_rank=0.0,
        combined_score=0.63,
    ),
    Candidate(
        product_id="p-run-short",
        name="TempoFlex Running Short",
        brand="Cymbal",
        category="Activewear",
        department="Women",
        retail_price=58.0,
        cost=26.0,
        description="Breathable short with a secure phone pocket.",
        image_uri="gs://retail-demo/products/run-short.png",
        vector_similarity=0.51,
        text_rank=0.1,
        combined_score=0.39,
    ),
]


class EmulatorCatalog:
    def search(self, request: ServeRequest) -> list[Candidate]:
        matches = [
            candidate
            for candidate in CATALOG
            if candidate.category == request.category
            and candidate.retail_price <= request.max_price
        ]
        return sorted(matches, key=lambda candidate: candidate.combined_score, reverse=True)

    def get_product(self, product_id: str) -> Candidate:
        for candidate in CATALOG:
            if candidate.product_id == product_id:
                return candidate
        raise RuntimeError(f"Unknown product: {product_id}")


class EmulatorFeatureStore:
    def __init__(self, now: datetime) -> None:
        self.rows = _feature_rows(now)

    def read_rows(self, row_keys: list[str], now: datetime) -> dict[str, FeatureRow]:
        return {row_key: self.rows[row_key] for row_key in row_keys if row_key in self.rows}

    def apply_event(self, product_id: str, event_type: str, occurred_at: datetime) -> FeatureRow:
        row_key = f"item#{product_id}"
        current = self.rows[row_key]
        values = dict(current.values)
        values["item_views_24h"] = int(values.get("item_views_24h", 0)) + 1
        if event_type == "item_purchased":
            values["item_units_sold_7d"] = int(values.get("item_units_sold_7d", 0)) + 1
            inventory = int(values.get("item_inventory_on_hand", 0))
            values["item_inventory_on_hand"] = max(inventory - 1, 0)
        values["demand_slope_24h"] = round(float(values.get("demand_slope_24h", 0)) + 0.06, 2)
        updated = FeatureRow(entity_key=row_key, values=values, cell_timestamp=occurred_at)
        self.rows[row_key] = updated
        return updated


class EmulatorVertexScorer:
    def score(
        self,
        use_case: str,
        candidates: list[Candidate],
        features: dict[str, FeatureRow],
    ) -> list[VertexScore]:
        return [self._score_candidate(use_case, candidate, features) for candidate in candidates]

    def _score_candidate(
        self,
        use_case: str,
        candidate: Candidate,
        features: dict[str, FeatureRow],
    ) -> VertexScore:
        item = features[f"item#{candidate.product_id}"]
        demand = float(item.values.get("demand_slope_24h", 0))
        model_score = round(candidate.combined_score + demand * 0.14, 3)
        if use_case != "pricing":
            return VertexScore(product_id=candidate.product_id, score=model_score)
        final_price = candidate.retail_price * (1 + demand * 0.09)
        return VertexScore(
            product_id=candidate.product_id,
            score=model_score,
            final_price=final_price,
        )


class EmulatorPublisher:
    def __init__(self) -> None:
        self.count = 0

    def publish(self, message: dict[str, str]) -> str:
        self.count += 1
        return f"emulator-{self.count}"


def build_emulator_service(settings: Settings | None = None) -> RetailServingService:
    config = settings or Settings()
    return RetailServingService(
        EmulatorCatalog(),
        EmulatorFeatureStore(datetime(2026, 6, 4, 17, 0, tzinfo=UTC)),
        EmulatorVertexScorer(),
        EmulatorPublisher(),
        service_mode="emulator",
        freshness_sla_seconds=config.feature_freshness_sla_seconds,
    )


def _feature_rows(now: datetime) -> dict[str, FeatureRow]:
    return {
        "user#u-ada": FeatureRow(
            entity_key="user#u-ada",
            values={
                "user_price_tier": "balanced",
                "coupon_propensity": 0.72,
                "user_category_affinity": ["Outerwear", "Activewear"],
            },
            cell_timestamp=now,
        ),
        "item#p-trail-jacket": _item("p-trail-jacket", now, 38, 14, 73, 0.42, 5.2),
        "item#p-urban-fleece": _item("p-urban-fleece", now, 24, 11, 88, 0.29, 8.0),
        "item#p-run-short": _item("p-run-short", now, 63, 31, 42, 0.58, 1.4),
    }


def _item(
    product_id: str,
    now: datetime,
    views: int,
    units: int,
    inventory: int,
    slope: float,
    pressure: float,
) -> FeatureRow:
    return FeatureRow(
        entity_key=f"item#{product_id}",
        values={
            "item_views_24h": views,
            "item_units_sold_7d": units,
            "item_inventory_on_hand": inventory,
            "demand_slope_24h": slope,
            "inventory_pressure": pressure,
        },
        cell_timestamp=now,
    )
