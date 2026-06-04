from app.config import Settings


def test_emulator_mode_has_no_required_cloud_targets() -> None:
    settings = Settings(serving_mode="emulator")

    assert settings.missing_live_fields() == []
    assert settings.api_status()["servingMode"] == "emulator"


def test_live_mode_reports_each_missing_gcp_target() -> None:
    settings = Settings(serving_mode="live", gcp_project="retail-demo")

    assert settings.missing_live_fields() == [
        "gcp_region",
        "bt_instance",
        "pubsub_topic",
        "alloydb_host",
        "alloydb_database",
        "alloydb_user",
        "vertex_ranking_endpoint",
        "vertex_pricing_endpoint",
        "vertex_coupon_endpoint",
        "alloydb_password or alloydb_password_secret",
    ]


def test_live_mode_accepts_password_or_secret_for_alloydb() -> None:
    settings = Settings(
        serving_mode="live",
        gcp_project="retail-demo",
        gcp_region="us-central1",
        bq_dataset="retail_demo",
        bt_instance="retail-features",
        bt_table="online_features",
        pubsub_topic="retail-events",
        alloydb_host="10.0.0.10",
        alloydb_database="retail",
        alloydb_user="retail_app",
        alloydb_password_secret="alloydb-password",
        vertex_ranking_endpoint="projects/p/locations/us/endpoints/1",
        vertex_pricing_endpoint="projects/p/locations/us/endpoints/2",
        vertex_coupon_endpoint="projects/p/locations/us/endpoints/3",
    )

    assert settings.missing_live_fields() == []
