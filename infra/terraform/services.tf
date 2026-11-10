# The eight services and the web UI. Each is one Code Engine app: one public address, and Code Engine
# runs between min_instances and max_instances copies of it, starting more when requests pile up.
# That is the load balancing: the registry stores the one address and Code Engine spreads requests
# over the copies.

resource "ibm_code_engine_app" "service" {
  for_each = local.services

  project_id      = ibm_code_engine_project.project.project_id
  name            = each.key
  image_reference = local.image[each.key]
  image_secret    = local.has_private_images ? ibm_code_engine_secret.images[0].name : null
  image_port      = 8000

  scale_min_instances      = var.min_instances
  scale_max_instances      = var.max_instances
  scale_concurrency        = var.target_concurrency * 2
  scale_concurrency_target = var.target_concurrency
  scale_cpu_limit          = var.cpu
  scale_memory_limit       = var.memory

  dynamic "run_env_variables" {
    for_each = merge({
      DATABASE_URL  = local.database_url[each.value.role]
      REDIS_URL     = local.redis_url
      AMQP_URL      = local.amqp_url
      REGISTRY_URLS = local.registry_urls
      REGISTRY_KEY  = local.registry_key
    }, local.tls_env)
    content {
      type  = "literal"
      name  = run_env_variables.key
      value = run_env_variables.value
    }
  }
}

resource "ibm_code_engine_app" "ui" {
  project_id      = ibm_code_engine_project.project.project_id
  name            = "ui"
  image_reference = local.image["ui"]
  image_secret    = local.has_private_images ? ibm_code_engine_secret.images[0].name : null
  image_port      = 8080

  scale_min_instances      = var.min_instances
  scale_max_instances      = var.max_instances
  scale_concurrency        = var.target_concurrency * 2
  scale_concurrency_target = var.target_concurrency
  scale_cpu_limit          = var.cpu
  scale_memory_limit       = var.memory

  dynamic "run_env_variables" {
    for_each = merge({
      REGISTRY_URLS = local.registry_urls
      AMQP_URL      = local.amqp_url
    }, local.tls_env)
    content {
      type  = "literal"
      name  = run_env_variables.key
      value = run_env_variables.value
    }
  }
}
