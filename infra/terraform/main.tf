data "ibm_resource_group" "group" {
  name = var.resource_group
}

resource "ibm_code_engine_project" "project" {
  name              = "${var.name_prefix}-platform"
  resource_group_id = data.ibm_resource_group.group.id
}

# Secrets generated here, so nothing sensitive is committed.
resource "random_password" "registry_key" {
  length  = 32
  special = false
}

resource "random_password" "role" {
  for_each = toset(["svc_reader", "svc_s6", "svc_s8", "ingestor"])
  length   = 24
  special  = false
}

locals {
  registry_key = var.registry_key != "" ? var.registry_key : random_password.registry_key.result

  # Registries and every service are separate Code Engine apps. Each gets its own address, which
  # Code Engine builds from CE_APP and CE_DOMAIN, so a service needs no address configured.
  image = { for n in concat(["registry", "ui", "ingestor", "db-init"], keys(local.services)) :
    n => "${var.image_prefix}/${var.name_prefix}-${n}:${var.image_tag}" }

  # name => which Python package it runs and which database role it uses
  services = {
    "price-history"   = { module = "price_history", role = "svc_reader" }
    "performance"     = { module = "performance", role = "svc_reader" }
    "volatility-risk" = { module = "volatility_risk", role = "svc_reader" }
    "indicators"      = { module = "indicators", role = "svc_reader" }
    "fund-builder"    = { module = "fund_builder", role = "svc_reader" }
    "portfolio"       = { module = "portfolio", role = "svc_s6" }
    "correlation"     = { module = "correlation_svc", role = "svc_reader" }
    "alerts-monitor"  = { module = "alerts_monitor", role = "svc_s8" }
  }

  has_private_images = var.image_registry_username != ""
}

resource "ibm_code_engine_secret" "images" {
  count      = local.has_private_images ? 1 : 0
  project_id = ibm_code_engine_project.project.project_id
  name       = "image-pull"
  format     = "registry"

  data = {
    server   = var.image_registry_server
    username = var.image_registry_username
    password = var.image_registry_password
  }
}
