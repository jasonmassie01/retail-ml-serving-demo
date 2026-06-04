variable "project_id" {
  description = "Google Cloud project that hosts the demo."
  type        = string
}

variable "region" {
  description = "Primary region for Cloud Run, AlloyDB, Pub/Sub, and BigQuery jobs."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Primary Bigtable zone."
  type        = string
  default     = "us-central1-b"
}

variable "bq_location" {
  description = "BigQuery dataset location. Keep regionally compatible with Bigtable."
  type        = string
  default     = "US"
}

variable "dataset_id" {
  description = "BigQuery dataset for the offline store and feature registry."
  type        = string
  default     = "retail_demo"
}

variable "bq_connection_id" {
  description = "BigQuery connection ID for Vertex AI remote models."
  type        = string
  default     = "vertex_conn"
}

variable "bigtable_instance_id" {
  description = "Bigtable online feature store instance ID."
  type        = string
  default     = "retail-features"
}

variable "bigtable_cluster_id" {
  description = "Bigtable cluster ID."
  type        = string
  default     = "retail-features-c1"
}

variable "bigtable_table_id" {
  description = "Bigtable table for online features."
  type        = string
  default     = "online_features"
}

variable "bigtable_app_profile_id" {
  description = "Bigtable app profile used by the serving API and BigQuery exports."
  type        = string
  default     = "serving"
}

variable "alloydb_cluster_id" {
  description = "AlloyDB cluster ID."
  type        = string
  default     = "retail-catalog"
}

variable "alloydb_instance_id" {
  description = "AlloyDB primary instance ID."
  type        = string
  default     = "retail-catalog-primary"
}

variable "alloydb_database" {
  description = "AlloyDB database name used by bootstrap SQL."
  type        = string
  default     = "retail"
}

variable "alloydb_user" {
  description = "AlloyDB application user."
  type        = string
  default     = "retail_app"
}

variable "alloydb_password" {
  description = "Initial AlloyDB password. Prefer TF_VAR_alloydb_password."
  type        = string
  sensitive   = true
}

variable "api_image" {
  description = "Artifact Registry image URL for the FastAPI service."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "vertex_ranking_endpoint" {
  description = "Vertex AI endpoint resource for recommendations and search ranking."
  type        = string
  default     = ""
}

variable "vertex_pricing_endpoint" {
  description = "Vertex AI endpoint resource for dynamic pricing."
  type        = string
  default     = ""
}

variable "vertex_coupon_endpoint" {
  description = "Vertex AI endpoint resource for coupon propensity."
  type        = string
  default     = ""
}

variable "allow_public_invoker" {
  description = "Grant unauthenticated Cloud Run access for demo viewing."
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Protect stateful resources from accidental destroy."
  type        = bool
  default     = true
}
