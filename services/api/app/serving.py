from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from app.models import (
    Candidate,
    EventResponse,
    FeatureRow,
    FreshFeatureRow,
    FreshnessSummary,
    PriceDecision,
    RetrievalScore,
    ServeRequest,
    ServeResponse,
    ServingResult,
    TraceStage,
    VertexScore,
)

HYBRID_SEARCH_SQL = """SELECT product_id, name, retail_price,
       (1.0 - (embedding <=> $1)) AS vector_similarity,
       ts_rank(fts, plainto_tsquery('english', $2)) AS text_rank,
       (((1.0 - (embedding <=> $1)) * 0.7)
         + (ts_rank(fts, plainto_tsquery('english', $2)) * 0.3)) AS combined_score
FROM products
WHERE retail_price < $3 AND category = $4
ORDER BY combined_score DESC
LIMIT 100;"""


class CandidateStore(Protocol):
    def search(self, request: ServeRequest) -> list[Candidate]:
        """Return use-case candidates from AlloyDB."""

    def get_product(self, product_id: str) -> Candidate:
        """Return one catalog product by ID."""


class FeatureStore(Protocol):
    def read_rows(self, row_keys: list[str], now: datetime) -> dict[str, FeatureRow]:
        """Return Bigtable feature rows keyed by entity key."""

    def apply_event(self, product_id: str, event_type: str, occurred_at: datetime) -> FeatureRow:
        """Apply a live demo event to the online feature store."""


class VertexScorer(Protocol):
    def score(
        self,
        use_case: str,
        candidates: list[Candidate],
        features: dict[str, FeatureRow],
    ) -> list[VertexScore]:
        """Return Vertex AI endpoint scores."""


class EventPublisher(Protocol):
    def publish(self, message: dict[str, str]) -> str:
        """Publish a Pub/Sub event and return its ID."""


class RetailServingService:
    def __init__(
        self,
        catalog: CandidateStore,
        feature_store: FeatureStore,
        scorer: VertexScorer,
        publisher: EventPublisher,
        service_mode: str = "emulator",
        freshness_sla_seconds: int = 120,
    ) -> None:
        self.catalog = catalog
        self.feature_store = feature_store
        self.scorer = scorer
        self.publisher = publisher
        self.service_mode = service_mode
        self.freshness_sla_seconds = freshness_sla_seconds
        self.event_count = 0

    def serve(self, request: ServeRequest, now: datetime | None = None) -> ServeResponse:
        decision_time = now or datetime.now(UTC)
        candidates = self._retrieve_candidates(request)
        row_keys = self._row_keys(request.user_id, candidates)
        features = self.feature_store.read_rows(row_keys, decision_time)
        self._require_feature_rows(row_keys, features)
        scores = self.scorer.score(request.use_case, candidates, features)
        results = self._build_results(request, candidates, features, scores)
        freshness = self._freshness(
            [key for key in row_keys if key.startswith("item#")],
            features,
            decision_time,
        )

        return ServeResponse(
            service_mode=self.service_mode,
            use_case=request.use_case,
            results=results[:1] if request.use_case == "pricing" else results[:3],
            trace=_trace(request.use_case),
            online_features={
                "user": features[f"user#{request.user_id}"],
                "item": freshness.rows[0],
            },
            freshness=freshness,
            debug_sql=_debug_sql(request.use_case),
            event_count=self.event_count,
        )

    def publish_event(
        self,
        product_id: str,
        event_type: str,
        occurred_at: datetime,
    ) -> EventResponse:
        message = {
            "product_id": product_id,
            "event_type": event_type,
            "occurred_at": occurred_at.isoformat(),
        }
        event_id = self.publisher.publish(message)
        updated = self.feature_store.apply_event(product_id, event_type, occurred_at)
        self.event_count += 1

        return EventResponse(
            event_id=event_id,
            published=True,
            updated_feature=self._with_freshness(updated, occurred_at),
        )

    def _retrieve_candidates(self, request: ServeRequest) -> list[Candidate]:
        if request.use_case == "pricing":
            return [self.catalog.get_product(request.product_id)]
        return self.catalog.search(request)

    def _row_keys(self, user_id: str, candidates: list[Candidate]) -> list[str]:
        keys = [f"user#{user_id}"]
        keys.extend(f"item#{candidate.product_id}" for candidate in candidates)
        return list(dict.fromkeys(keys))

    def _require_feature_rows(
        self,
        row_keys: list[str],
        features: dict[str, FeatureRow],
    ) -> None:
        missing = [row_key for row_key in row_keys if row_key not in features]
        if missing:
            raise RuntimeError(f"Missing online feature rows: {', '.join(missing)}")

    def _build_results(
        self,
        request: ServeRequest,
        candidates: list[Candidate],
        features: dict[str, FeatureRow],
        scores: list[VertexScore],
    ) -> list[ServingResult]:
        score_by_product = {score.product_id: score for score in scores}
        results = [
            self._result(request, candidate, features, score_by_product)
            for candidate in candidates
        ]
        return sorted(results, key=lambda result: result.model_score, reverse=True)

    def _result(
        self,
        request: ServeRequest,
        candidate: Candidate,
        features: dict[str, FeatureRow],
        score_by_product: dict[str, VertexScore],
    ) -> ServingResult:
        fallback = VertexScore(product_id=candidate.product_id, score=0)
        vertex_score = score_by_product.get(candidate.product_id, fallback)
        item = features[f"item#{candidate.product_id}"]
        user = features[f"user#{request.user_id}"]
        return ServingResult(
            product=candidate,
            retrieval=RetrievalScore(
                vector_similarity=candidate.vector_similarity,
                text_rank=candidate.text_rank,
                combined_score=candidate.combined_score,
            ),
            model_score=round(vertex_score.score, 3),
            explanation=_explanation(candidate, item, user, request.use_case),
            price_decision=self._price_decision(candidate, vertex_score, user)
            if request.use_case == "pricing"
            else None,
        )

    def _price_decision(
        self,
        candidate: Candidate,
        score: VertexScore,
        user: FeatureRow,
    ) -> PriceDecision:
        floor_price = round(candidate.cost * 1.18, 2)
        proposed = score.final_price if score.final_price is not None else candidate.retail_price
        return PriceDecision(
            list_price=candidate.retail_price,
            final_price=round(max(proposed, floor_price), 2),
            floor_price=floor_price,
            coupon_tier=score.coupon_tier or _coupon_tier(user),
        )

    def _freshness(
        self,
        item_keys: list[str],
        features: dict[str, FeatureRow],
        now: datetime,
    ) -> FreshnessSummary:
        rows = [self._with_freshness(features[key], now) for key in item_keys]
        max_staleness = max((row.staleness_seconds for row in rows), default=0)
        status = "stale" if max_staleness > self.freshness_sla_seconds else "fresh"
        return FreshnessSummary(rows=rows, max_staleness_seconds=max_staleness, status=status)

    def _with_freshness(self, row: FeatureRow, now: datetime) -> FreshFeatureRow:
        staleness = max(int((now - row.cell_timestamp).total_seconds()), 0)
        status = "stale" if staleness > self.freshness_sla_seconds else "fresh"
        return FreshFeatureRow(
            entity_key=row.entity_key,
            values=row.values,
            cell_timestamp=row.cell_timestamp,
            staleness_seconds=staleness,
            status=status,
        )


def _trace(use_case: str) -> list[TraceStage]:
    return [
        TraceStage(
            service="BigQuery",
            operation="feature registry and query embedding",
            latency_ms=18,
        ),
        TraceStage(
            service="AlloyDB ScaNN",
            operation=f"{use_case} candidate generation",
            latency_ms=22,
        ),
        TraceStage(
            service="Bigtable",
            operation="entity-keyed online feature lookups",
            latency_ms=3,
        ),
        TraceStage(
            service="Vertex AI",
            operation=f"{use_case} score/rank endpoint",
            latency_ms=31,
        ),
    ]


def _debug_sql(use_case: str) -> str:
    if use_case == "search":
        return HYBRID_SEARCH_SQL
    if use_case == "pricing":
        return "pricing = Vertex endpoint bounded by cost + margin; coupon = BQML propensity"
    return "recommendations = ScaNN seed candidates + Bigtable features + Vertex ranker"


def _explanation(candidate: Candidate, item: FeatureRow, user: FeatureRow, use_case: str) -> str:
    if use_case == "search" and candidate.product_id == "p-trail-jacket":
        return "keyword rank preserved while vector similarity stays in the blended score."
    pressure = item.values.get("inventory_pressure", 0)
    slope = item.values.get("demand_slope_24h", 0)
    tier = user.values.get("user_price_tier", "unknown")
    return (
        f"{candidate.category} affinity, inventory pressure {pressure}, "
        f"demand slope {slope}, and {tier} tier."
    )


def _coupon_tier(user: FeatureRow) -> str:
    propensity = float(user.values.get("coupon_propensity", 0))
    price_tier = str(user.values.get("user_price_tier", "balanced"))
    if propensity >= 0.85 or price_tier == "value":
        return "15% loyalty coupon"
    if propensity >= 0.65:
        return "10% basket coupon"
    return "no coupon"
