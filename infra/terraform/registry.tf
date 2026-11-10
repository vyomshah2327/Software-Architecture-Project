# Two identical registry apps. Both read and write the same Redis, so either one can answer.
# Names are fixed (not for_each) so the other apps can refer to both addresses.

locals {
  registry_env = merge({
    REDIS_URL       = local.redis_url
    AMQP_URL        = local.amqp_url
    REGISTRY_KEY    = local.registry_key
    ALLOWED_DOMAINS = "appdomain.cloud"
  }, local.tls_env)
}

resource "ibm_code_engine_app" "registry_primary" {
  project_id      = ibm_code_engine_project.project.project_id
  name            = "registry-primary"
  image_reference = local.image["registry"]
  image_secret    = local.has_private_images ? ibm_code_engine_secret.images[0].name : null
  image_port      = 8000

  scale_min_instances      = 1
  scale_max_instances      = 2
  scale_concurrency        = 50
  scale_concurrency_target = 25
  scale_cpu_limit          = var.cpu
  scale_memory_limit       = var.memory

  dynamic "run_env_variables" {
    for_each = local.registry_env
    content {
      type  = "literal"
      name  = run_env_variables.key
      value = run_env_variables.value
    }
  }
}

resource "ibm_code_engine_app" "registry_backup" {
  project_id      = ibm_code_engine_project.project.project_id
  name            = "registry-backup"
  image_reference = local.image["registry"]
  image_secret    = local.has_private_images ? ibm_code_engine_secret.images[0].name : null
  image_port      = 8000

  scale_min_instances      = 1
  scale_max_instances      = 2
  scale_concurrency        = 50
  scale_concurrency_target = 25
  scale_cpu_limit          = var.cpu
  scale_memory_limit       = var.memory

  dynamic "run_env_variables" {
    for_each = local.registry_env
    content {
      type  = "literal"
      name  = run_env_variables.key
      value = run_env_variables.value
    }
  }
}

locals {
  registry_urls = "${ibm_code_engine_app.registry_primary.endpoint},${ibm_code_engine_app.registry_backup.endpoint}"
}
