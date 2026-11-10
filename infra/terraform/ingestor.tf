# Schema job (run once after the database exists) and the daily ingestion job on a schedule.

resource "ibm_code_engine_job" "db_init" {
  project_id      = ibm_code_engine_project.project.project_id
  name            = "db-init"
  image_reference = local.image["db-init"]
  image_secret    = local.has_private_images ? ibm_code_engine_secret.images[0].name : null

  dynamic "run_env_variables" {
    for_each = merge(
      { DATABASE_URL = local.database_admin_url },
      { for role, pw in random_password.role : "ROLE_PASSWORD_${upper(role)}" => pw.result }
    )
    content {
      type  = "literal"
      name  = run_env_variables.key
      value = run_env_variables.value
    }
  }
}

resource "ibm_code_engine_job" "ingestor" {
  project_id      = ibm_code_engine_project.project.project_id
  name            = "market-data-ingestor"
  image_reference = local.image["ingestor"]
  image_secret    = local.has_private_images ? ibm_code_engine_secret.images[0].name : null

  dynamic "run_env_variables" {
    for_each = merge({
      DATABASE_URL     = local.database_url["ingestor"]
      AMQP_URL         = local.amqp_url
      DATA_SOURCE      = var.data_source
      ALPHAVANTAGE_KEY = var.alphavantage_key
      DAILY_API_LIMIT  = "25"
      PER_MINUTE_LIMIT = "5"
    }, local.archive_env, local.tls_env)
    content {
      type  = "literal"
      name  = run_env_variables.key
      value = run_env_variables.value
    }
  }
}

resource "ibm_code_engine_subscription_cron" "daily_ingest" {
  project_id       = ibm_code_engine_project.project.project_id
  name             = "daily-ingest"
  destination_type = "job"
  destination      = ibm_code_engine_job.ingestor.name
  schedule         = var.ingest_schedule
  time_zone        = "UTC"
}
