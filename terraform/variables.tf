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
