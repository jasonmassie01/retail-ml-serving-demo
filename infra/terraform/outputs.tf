output "artifact_registry_repository" {
  value = google_artifact_registry_repository.containers.name
}

output "api_service_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "alloydb_loader_job" {
  value = google_cloud_run_v2_job.alloydb_loader.name
}

output "api_service_account" {
  value = google_service_account.api.email
}

output "pipeline_service_account" {
  value = google_service_account.pipeline.email
}

output "bigquery_dataset" {
  value = google_bigquery_dataset.retail.dataset_id
}

output "bigquery_connection" {
  value = google_bigquery_connection.vertex.name
}

output "bigtable_feature_uri" {
  value = join("", [
    "https://bigtable.googleapis.com/projects/${var.project_id}",
    "/instances/${var.bigtable_instance_id}",
    "/appProfiles/${var.bigtable_app_profile_id}",
    "/tables/${var.bigtable_table_id}",
  ])
}

output "alloydb_private_ip" {
  value = google_alloydb_instance.primary.ip_address
}
