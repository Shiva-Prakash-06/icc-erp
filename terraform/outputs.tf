output "service_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "database_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}

output "scheduler_service_account" {
  value = google_service_account.scheduler.email
}

output "migration_job_name" {
  value = google_cloud_run_v2_job.migration.name
}

output "import_commit_job_name" {
  value = google_cloud_run_v2_job.import_commit.name
}

output "artifact_repository" {
  value = google_artifact_registry_repository.application.name
}
