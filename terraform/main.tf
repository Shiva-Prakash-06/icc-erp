locals {
  name = "icc-erp-${var.environment}"
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "random_password" "database" {
  length  = 32
  special = true
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "google_sql_database_instance" "postgres" {
  name                = local.name
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = var.environment == "production"

  settings {
    tier              = var.database_tier
    availability_type = var.environment == "production" ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "20:00"
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
      }
    }

    maintenance_window {
      day  = 7
      hour = 21
    }

    insights_config {
      query_insights_enabled = true
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "application" {
  name     = var.database_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "application" {
  name     = var.database_user
  instance = google_sql_database_instance.postgres.name
  password = random_password.database.result
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "${local.name}-database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql+psycopg://${var.database_user}:${urlencode(random_password.database.result)}@/${var.database_name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
}

resource "google_secret_manager_secret" "secret_key" {
  secret_id = "${local.name}-secret-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "secret_key" {
  secret      = google_secret_manager_secret.secret_key.id
  secret_data = random_password.secret_key.result
}

resource "google_service_account" "runtime" {
  account_id   = replace(local.name, "_", "-")
  display_name = "ICC ERP ${var.environment} runtime"
}

resource "google_project_iam_member" "sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "web" {
  name     = local.name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = var.environment == "production" ? 1 : 0
      max_instance_count = 10
    }

    containers {
      image = var.image
      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }

      env {
        name  = "APP_ENV"
        value = var.environment
      }
      env {
        name  = "DEMONSTRATOR"
        value = var.environment == "production" ? "false" : "true"
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        failure_threshold     = 10
      }
      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        period_seconds  = 30
        timeout_seconds = 3
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }
  }
  depends_on = [google_project_service.apis]
}

# Cloud Run authenticates transport while the ERP enforces user authentication,
# scoped authorization, CSRF, and rate limits at the application boundary.
resource "google_cloud_run_v2_service_iam_member" "web_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.web.location
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_tasks_queue" "jobs" {
  name     = "${local.name}-jobs"
  location = var.region
  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 10
  }
  retry_config {
    max_attempts = 5
    min_backoff  = "5s"
    max_backoff  = "300s"
  }
}

resource "google_cloud_scheduler_job" "reminders" {
  name        = "${local.name}-reminders"
  description = "Daily deadline, closure, and archival reminder trigger"
  schedule    = "30 8 * * *"
  time_zone   = "Asia/Kolkata"
  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.web.uri}/internal/jobs/reminders"
    oidc_token {
      service_account_email = google_service_account.runtime.email
      audience              = google_cloud_run_v2_service.web.uri
    }
  }
}

resource "google_monitoring_uptime_check_config" "web" {
  display_name = "${local.name} health"
  timeout      = "10s"
  period       = "60s"
  http_check {
    path         = "/healthz"
    port         = "443"
    use_ssl      = true
    validate_ssl = true
  }
  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.web.uri, "https://")
    }
  }
}
