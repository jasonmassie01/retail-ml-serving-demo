from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

UseCase = Literal["recommendations", "search", "pricing"]
EventType = Literal["product_viewed", "item_purchased"]
FeatureStatus = Literal["fresh", "stale"]
ServiceName = Literal["BigQuery", "AlloyDB ScaNN", "Bigtable", "Vertex AI"]


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ServeRequest(ApiModel):
    use_case: UseCase = "recommendations"
    user_id: str = "u-ada"
    query: str = ""
    category: str = "Outerwear"
    max_price: float = Field(default=160.0, gt=0)
    product_id: str = "p-trail-jacket"


FeatureValue = str | int | float | bool | list[str]


class Candidate(ApiModel):
    product_id: str
    name: str
    brand: str
    category: str
    department: str
    retail_price: float
    cost: float
    description: str
    image_uri: str = ""
    vector_similarity: float = 0
    text_rank: float = 0
    combined_score: float = 0


class FeatureRow(ApiModel):
    entity_key: str
    values: dict[str, FeatureValue]
    cell_timestamp: datetime


class FreshFeatureRow(FeatureRow):
    staleness_seconds: int
    status: FeatureStatus


class VertexScore(ApiModel):
    product_id: str
    score: float
    final_price: float | None = None
    coupon_tier: str | None = None


class RetrievalScore(ApiModel):
    vector_similarity: float
    text_rank: float
    combined_score: float


class PriceDecision(ApiModel):
    list_price: float
    final_price: float
    floor_price: float
    coupon_tier: str


class ServingResult(ApiModel):
    product: Candidate
    retrieval: RetrievalScore
    model_score: float
    explanation: str
    price_decision: PriceDecision | None = None


class TraceStage(ApiModel):
    service: ServiceName
    operation: str
    latency_ms: int


class FreshnessSummary(ApiModel):
    rows: list[FreshFeatureRow]
    max_staleness_seconds: int
    status: FeatureStatus


class ServeResponse(ApiModel):
    service_mode: Literal["emulator", "live"]
    use_case: UseCase
    results: list[ServingResult]
    trace: list[TraceStage]
    online_features: dict[str, FeatureRow]
    freshness: FreshnessSummary
    debug_sql: str
    event_count: int


class EventRequest(ApiModel):
    product_id: str
    event_type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class EventResponse(ApiModel):
    event_id: str
    published: bool
    updated_feature: FreshFeatureRow
