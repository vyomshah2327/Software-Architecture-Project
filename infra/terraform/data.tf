# PostgreSQL, Redis, RabbitMQ and Object Storage. With data_mode = "external" none of this is created
# and the URLs in the variables are used instead.

resource "random_password" "db_admin" {
  length  = 24
  special = false
}

resource "ibm_database" "postgres" {
  count             = var.data_mode == "managed" ? 1 : 0
  name              = "${var.name_prefix}-postgres"
  service           = "databases-for-postgresql"
  plan              = "standard"
  location          = var.region
  resource_group_id = data.ibm_resource_group.group.id
  adminpassword     = random_password.db_admin.result
  service_endpoints = "public"

  group {
    group_id = "member"
    memory { allocation_mb = 3072 }
    disk { allocation_mb = 15360 }
  }
}

resource "ibm_database" "redis" {
  count             = var.data_mode == "managed" ? 1 : 0
  name              = "${var.name_prefix}-redis"
  service           = "databases-for-redis"
  plan              = "standard"
  location          = var.region
  resource_group_id = data.ibm_resource_group.group.id
  adminpassword     = random_password.db_admin.result
  service_endpoints = "public"

  group {
    group_id = "member"
    memory { allocation_mb = 2048 }
    disk { allocation_mb = 2048 }
  }
}

resource "ibm_database" "rabbitmq" {
  count             = var.data_mode == "managed" ? 1 : 0
  name              = "${var.name_prefix}-rabbitmq"
  service           = "messages-for-rabbitmq"
  plan              = "standard"
  location          = var.region
  resource_group_id = data.ibm_resource_group.group.id
  adminpassword     = random_password.db_admin.result
  service_endpoints = "public"

  group {
    group_id = "member"
    memory { allocation_mb = 3072 }
    disk { allocation_mb = 3072 }
  }
}

resource "ibm_resource_instance" "cos" {
  count             = var.data_mode == "managed" ? 1 : 0
  name              = "${var.name_prefix}-object-storage"
  service           = "cloud-object-storage"
  plan              = "standard"
  location          = "global"
  resource_group_id = data.ibm_resource_group.group.id
}

resource "ibm_cos_bucket" "archive" {
  count                = var.data_mode == "managed" ? 1 : 0
  bucket_name          = "${var.name_prefix}-raw-${substr(md5(ibm_code_engine_project.project.id), 0, 8)}"
  resource_instance_id = ibm_resource_instance.cos[0].id
  region_location      = var.region
  storage_class        = "smart"
}

resource "ibm_resource_key" "cos" {
  count                = var.data_mode == "managed" ? 1 : 0
  name                 = "${var.name_prefix}-cos-key"
  role                 = "Writer"
  resource_instance_id = ibm_resource_instance.cos[0].id
  parameters           = { HMAC = true }
}

locals {
  managed = var.data_mode == "managed"

  pg_host = local.managed ? ibm_database.postgres[0].connectionstrings[0].hosts[0].hostname : ""
  pg_port = local.managed ? ibm_database.postgres[0].connectionstrings[0].hosts[0].port : 0

  # One URL per database role, so each service connects with only the rights it needs.
  database_admin_url = local.managed ? "postgresql://admin:${random_password.db_admin.result}@${local.pg_host}:${local.pg_port}/ibmclouddb?sslmode=require" : var.external_database_admin_url

  database_host_part = local.managed ? "${local.pg_host}:${local.pg_port}/ibmclouddb?sslmode=require" : regex("@(.*)$", var.external_database_admin_url)[0]

  database_url = { for role, pw in random_password.role :
  role => "postgresql://${role}:${pw.result}@${local.database_host_part}" }

  redis_url = local.managed ? "rediss://admin:${random_password.db_admin.result}@${ibm_database.redis[0].connectionstrings[0].hosts[0].hostname}:${ibm_database.redis[0].connectionstrings[0].hosts[0].port}/0?ssl_cert_reqs=none" : var.external_redis_url

  amqp_url = local.managed ? "amqps://admin:${random_password.db_admin.result}@${ibm_database.rabbitmq[0].connectionstrings[0].hosts[0].hostname}:${ibm_database.rabbitmq[0].connectionstrings[0].hosts[0].port}/" : var.external_amqp_url

  # The managed brokers use a private certificate authority. Fine for a demo; for production mount its certificate.
  tls_env = local.managed ? { AMQP_TLS_VERIFY = "false" } : {}

  archive_env = local.managed ? {
    ARCHIVE_BUCKET     = ibm_cos_bucket.archive[0].bucket_name
    ARCHIVE_ENDPOINT   = "https://${ibm_cos_bucket.archive[0].s3_endpoint_public}"
    ARCHIVE_ACCESS_KEY = ibm_resource_key.cos[0].credentials["cos_hmac_keys.access_key_id"]
    ARCHIVE_SECRET_KEY = ibm_resource_key.cos[0].credentials["cos_hmac_keys.secret_access_key"]
  } : {}
}
