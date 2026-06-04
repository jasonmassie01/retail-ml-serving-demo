from __future__ import annotations

import os
from dataclasses import dataclass

LIVE_REQUIRED_FIELDS = [
    "gcp_project",
    "gcp_region",
    "bq_dataset",
    "bt_instance",
    "bt_table",
    "pubsub_topic",
    "alloydb_host",
    "alloydb_database",
    "alloydb_user",
    "vertex_ranking_endpoint",
    "vertex_pricing_endpoint",
    "vertex_coupon_endpoint",
]


@dataclass(frozen=True)
class Settings:
    serving_mode: str = "emulator"
    gcp_project: str = ""
    gcp_region: str = ""
    bq_dataset: str = "retail_demo"
    bq_location: str = "US"
    bq_embedding_model: str = "gemini_embed"
    bt_instance: str = ""
    bt_table: str = "online_features"
    bt_app_profile: str = "default"
    bt_column_family: str = "f"
    pubsub_topic: str = ""
    alloydb_host: str = ""
    alloydb_port: int = 5432
    alloydb_database: str = ""
    alloydb_user: str = ""
    alloydb_password: str = ""
    alloydb_password_secret: str = ""
    vertex_ranking_endpoint: str = ""
    vertex_pricing_endpoint: str = ""
    vertex_coupon_endpoint: str = ""
    feature_freshness_sla_seconds: int = 120

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            serving_mode=_env("SERVING_MODE", "emulator"),
            gcp_project=_env("GCP_PROJECT") or _env("GOOGLE_CLOUD_PROJECT"),
            gcp_region=_env("GCP_REGION") or _env("GOOGLE_CLOUD_REGION"),
            bq_dataset=_env("BQ_DATASET", "retail_demo"),
            bq_location=_env("BQ_LOCATION", "US"),
            bq_embedding_model=_env("BQ_EMBEDDING_MODEL", "gemini_embed"),
            bt_instance=_env("BT_INSTANCE") or _env("BIGTABLE_INSTANCE_ID"),
            bt_table=_env("BT_TABLE") or _env("BIGTABLE_FEATURE_TABLE", "online_features"),
            bt_app_profile=_env("BT_APP_PROFILE", "default"),
            bt_column_family=_env("BT_COLUMN_FAMILY", "f"),
            pubsub_topic=_env("PUBSUB_TOPIC") or _env("EVENT_TOPIC"),
            alloydb_host=_env("ALLOYDB_HOST"),
            alloydb_port=int(_env("ALLOYDB_PORT", "5432")),
            alloydb_database=_env("ALLOYDB_DATABASE"),
            alloydb_user=_env("ALLOYDB_USER"),
            alloydb_password=_env("ALLOYDB_PASSWORD"),
            alloydb_password_secret=_env("ALLOYDB_PASSWORD_SECRET"),
            vertex_ranking_endpoint=_env("VERTEX_RANKING_ENDPOINT"),
            vertex_pricing_endpoint=_env("VERTEX_PRICING_ENDPOINT"),
            vertex_coupon_endpoint=_env("VERTEX_COUPON_ENDPOINT"),
            feature_freshness_sla_seconds=int(_env("FEATURE_FRESHNESS_SLA_SECONDS", "120")),
        )

    def missing_live_fields(self) -> list[str]:
        if self.serving_mode != "live":
            return []

        missing = [field for field in LIVE_REQUIRED_FIELDS if not getattr(self, field)]
        if not self.alloydb_password and not self.alloydb_password_secret:
            missing.append("alloydb_password or alloydb_password_secret")
        return missing

    def api_status(self) -> dict[str, object]:
        return {
            "servingMode": self.serving_mode,
            "missingLiveFields": self.missing_live_fields(),
        }


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()
