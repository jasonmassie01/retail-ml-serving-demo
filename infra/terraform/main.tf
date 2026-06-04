locals {
  services = toset([
    "aiplatform.googleapis.com",
    "alloydb.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "bigtable.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "vpcaccess.googleapis.com",
  ])
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "apis" {
  for_each           = local.services
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "api" {
  account_id   = "retail-serving-api"
  display_name = "Retail ML Serving API"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "pipeline" {
  account_id   = "retail-feature-pipeline"
  display_name = "Retail ML feature pipeline"
  depends_on   = [google_project_service.apis]
}

resource "google_compute_network" "demo" {
  name                    = "retail-ml-demo"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "demo" {
  name          = "retail-ml-demo"
  ip_cidr_range = "10.42.0.0/24"
  network       = google_compute_network.demo.id
  region        = var.region
}

resource "google_compute_global_address" "private_service_access" {
  name          = "retail-ml-demo-psa"
  address_type  = "INTERNAL"
  purpose       = "VPC_PEERING"
  prefix_length = 16
  network       = google_compute_network.demo.id
}

resource "google_service_networking_connection" "private_service_access" {
  network                 = google_compute_network.demo.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access.name]
}

resource "google_vpc_access_connector" "api" {
  name          = "retail-api-vpc"
  region        = var.region
  network       = google_compute_network.demo.name
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 3
}

resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = "retail-ml-demo"
  description   = "Retail ML serving demo containers"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

resource "google_bigquery_dataset" "retail" {
  dataset_id                 = var.dataset_id
  location                   = var.bq_location
  delete_contents_on_destroy = !var.deletion_protection
  description                = "Retail ML demo offline feature store and pipeline data"
}

resource "google_bigquery_connection" "vertex" {
  connection_id = var.bq_connection_id
  location      = var.bq_location
  description   = "Remote model connection for Gemini embeddings and enrichment"

  cloud_resource {}
}

resource "google_bigquery_table" "feature_registry" {
  dataset_id = google_bigquery_dataset.retail.dataset_id
  table_id   = "feature_registry"
  schema     = file("${path.module}/schemas/feature_registry.json")
}

resource "google_bigquery_table" "live_events" {
  dataset_id          = google_bigquery_dataset.retail.dataset_id
  table_id            = "live_events"
  deletion_protection = var.deletion_protection
  schema              = file("${path.module}/schemas/live_events.json")
  time_partitioning {
    type  = "DAY"
    field = "occurred_at"
  }
}

resource "google_bigquery_table" "item_features_current" {
  dataset_id = google_bigquery_dataset.retail.dataset_id
  table_id   = "item_features_current"
  schema     = file("${path.module}/schemas/item_features_current.json")
}

resource "google_bigquery_table" "user_features_current" {
  dataset_id = google_bigquery_dataset.retail.dataset_id
  table_id   = "user_features_current"
  schema     = file("${path.module}/schemas/user_features_current.json")
}

resource "google_bigtable_instance" "features" {
  name                = var.bigtable_instance_id
  deletion_protection = var.deletion_protection
  edition             = "ENTERPRISE_PLUS"

  cluster {
    cluster_id   = var.bigtable_cluster_id
    zone         = var.zone
    num_nodes    = 1
    storage_type = "SSD"
  }

  labels = {
    app = "retail-ml-demo"
  }
}

resource "google_bigtable_table" "online_features" {
  name          = var.bigtable_table_id
  instance_name = google_bigtable_instance.features.name

  column_family {
    family = "f"
  }
}

resource "google_bigtable_app_profile" "serving" {
  instance       = google_bigtable_instance.features.name
  app_profile_id = var.bigtable_app_profile_id

  single_cluster_routing {
    cluster_id                 = var.bigtable_cluster_id
    allow_transactional_writes = true
  }

  ignore_warnings = true
}

resource "google_pubsub_topic" "events" {
  name = "retail-live-events"
}

resource "google_pubsub_topic" "events_dead_letter" {
  name = "retail-live-events-dlq"
}

resource "google_project_iam_member" "pubsub_bigquery_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member = format(
    "serviceAccount:service-%s@gcp-sa-pubsub.iam.gserviceaccount.com",
    data.google_project.current.number,
  )
}

resource "google_pubsub_subscription" "events_to_bigquery" {
  name  = "retail-live-events-to-bigquery"
  topic = google_pubsub_topic.events.id

  bigquery_config {
    table            = "${var.project_id}:${var.dataset_id}.live_events"
    use_table_schema = true
    write_metadata   = true
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.events_dead_letter.id
    max_delivery_attempts = 5
  }

  depends_on = [
    google_bigquery_table.live_events,
    google_project_iam_member.pubsub_bigquery_writer,
  ]
}

resource "google_secret_manager_secret" "alloydb_password" {
  secret_id = "retail-alloydb-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "alloydb_password" {
  secret      = google_secret_manager_secret.alloydb_password.id
  secret_data = var.alloydb_password
}

resource "google_alloydb_cluster" "catalog" {
  cluster_id          = var.alloydb_cluster_id
  location            = var.region
  database_version    = "POSTGRES_15"
  deletion_protection = var.deletion_protection

  network_config {
    network = google_compute_network.demo.id
  }

  initial_user {
    user     = var.alloydb_user
    password = var.alloydb_password
  }

  depends_on = [google_service_networking_connection.private_service_access]
}

resource "google_alloydb_instance" "primary" {
  cluster       = google_alloydb_cluster.catalog.name
  instance_id   = var.alloydb_instance_id
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = 2
  }
}

resource "google_cloud_run_v2_service" "api" {
  name     = "retail-ml-serving-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      env {
        name  = "SERVING_MODE"
        value = "live"
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "BQ_DATASET"
        value = google_bigquery_dataset.retail.dataset_id
      }
      env {
        name  = "BQ_LOCATION"
        value = var.bq_location
      }
      env {
        name  = "BT_INSTANCE"
        value = google_bigtable_instance.features.name
      }
      env {
        name  = "BT_TABLE"
        value = google_bigtable_table.online_features.name
      }
      env {
        name  = "BT_APP_PROFILE"
        value = google_bigtable_app_profile.serving.app_profile_id
      }
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.events.name
      }
      env {
        name  = "ALLOYDB_HOST"
        value = google_alloydb_instance.primary.ip_address
      }
      env {
        name  = "ALLOYDB_DATABASE"
        value = var.alloydb_database
      }
      env {
        name  = "ALLOYDB_USER"
        value = var.alloydb_user
      }
      env {
        name  = "ALLOYDB_PASSWORD_SECRET"
        value = google_secret_manager_secret.alloydb_password.secret_id
      }
      env {
        name  = "VERTEX_RANKING_ENDPOINT"
        value = var.vertex_ranking_endpoint
      }
      env {
        name  = "VERTEX_PRICING_ENDPOINT"
        value = var.vertex_pricing_endpoint
      }
      env {
        name  = "VERTEX_COUPON_ENDPOINT"
        value = var.vertex_coupon_endpoint
      }
    }

    vpc_access {
      connector = google_vpc_access_connector.api.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
  }

  depends_on = [
    google_alloydb_instance.primary,
    google_project_iam_member.api_roles,
  ]
}

resource "google_cloud_run_service_iam_member" "public_invoker" {
  count    = var.allow_public_invoker ? 1 : 0
  service  = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/bigquery.jobUser",
    "roles/bigquery.dataViewer",
    "roles/bigtable.user",
    "roles/pubsub.publisher",
    "roles/secretmanager.secretAccessor",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "pipeline_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/bigquery.jobUser",
    "roles/bigquery.dataEditor",
    "roles/bigtable.user",
    "roles/pubsub.publisher",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "bq_connection_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member = format(
    "serviceAccount:%s",
    google_bigquery_connection.vertex.cloud_resource[0].service_account_id,
  )
}
