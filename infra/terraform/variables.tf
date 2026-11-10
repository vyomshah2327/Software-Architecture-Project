variable "ibmcloud_api_key" {
  description = "IBM Cloud API key. Set with TF_VAR_ibmcloud_api_key, never write it in a file."
  type        = string
  sensitive   = true
}

variable "region" {
  description = "IBM Cloud region for Code Engine and the data services."
  type        = string
  default     = "ca-tor"
}

variable "resource_group" {
  description = "Resource group to create everything in."
  type        = string
  default     = "default"
}

variable "name_prefix" {
  description = "Prefix for resource names, so several copies can live in one account."
  type        = string
  default     = "stock"
}

# ---------------------------------------------------------------- images
variable "image_prefix" {
  description = "Where the images live, without the name, for example ghcr.io/vyomshah2327"
  type        = string
  default     = "ghcr.io/vyomshah2327"
}

variable "image_tag" {
  description = "Tag of the images to deploy. The pipeline pushes the commit id and latest."
  type        = string
  default     = "latest"
}

variable "image_registry_server" {
  description = "Registry host, used only when the images are private."
  type        = string
  default     = "ghcr.io"
}

variable "image_registry_username" {
  description = "Leave empty when the images are public."
  type        = string
  default     = ""
}

variable "image_registry_password" {
  description = "Registry token for private images."
  type        = string
  default     = ""
  sensitive   = true
}

# ---------------------------------------------------------------- autoscaling
variable "min_instances" {
  description = "Copies always running for each service."
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Most copies Code Engine may start for each service. Use 1 for the 'without scaling' load test."
  type        = number
  default     = 5
}

variable "target_concurrency" {
  description = "Requests per copy that trigger starting another copy."
  type        = number
  default     = 10
}

variable "cpu" {
  type    = string
  default = "0.25"
}

variable "memory" {
  type    = string
  default = "0.5G"
}

# ---------------------------------------------------------------- data services
variable "data_mode" {
  description = "managed: create PostgreSQL, Redis, RabbitMQ and Object Storage on IBM Cloud. external: use the three URLs below, for example a VM running docker compose."
  type        = string
  default     = "managed"

  validation {
    condition     = contains(["managed", "external"], var.data_mode)
    error_message = "data_mode must be managed or external."
  }
}

variable "external_database_admin_url" {
  description = "Only for data_mode external: PostgreSQL URL of a user who may create roles."
  type        = string
  default     = ""
  sensitive   = true
}

variable "external_redis_url" {
  type      = string
  default   = ""
  sensitive = true
}

variable "external_amqp_url" {
  type      = string
  default   = ""
  sensitive = true
}

# ---------------------------------------------------------------- application
variable "registry_key" {
  description = "Shared secret that services use to register. Leave empty to generate one."
  type        = string
  default     = ""
  sensitive   = true
}

variable "data_source" {
  description = "fake for demos, alphavantage for real prices."
  type        = string
  default     = "fake"
}

variable "alphavantage_key" {
  type      = string
  default   = "demo"
  sensitive = true
}

variable "ingest_schedule" {
  description = "Cron schedule (UTC) of the daily ingestion job."
  type        = string
  default     = "0 22 * * 1-5"
}
