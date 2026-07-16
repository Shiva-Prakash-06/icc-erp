variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-south1"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

variable "image" {
  type = string
}

variable "database_tier" {
  type    = string
  default = "db-custom-2-7680"
}

variable "database_name" {
  type    = string
  default = "icc_erp"
}

variable "database_user" {
  type    = string
  default = "icc_erp"
}

variable "drive_credentials_json" {
  type      = string
  sensitive = true
}

variable "smtp_username" {
  type = string
}

variable "smtp_host" {
  type = string
}

variable "smtp_port" {
  type    = number
  default = 587
}

variable "smtp_use_tls" {
  type    = bool
  default = true
}

variable "smtp_password" {
  type      = string
  sensitive = true
}

variable "smtp_from_address" {
  type = string
}

variable "notification_email_mode" {
  type    = string
  default = "smtp"
}

variable "alert_email" {
  type = string
}

variable "internal_job_base_url" {
  type        = string
  description = "Stable HTTPS Cloud Run URL or approved custom domain used as the OIDC audience."
}

variable "min_instances" {
  type    = number
  default = 1
}
