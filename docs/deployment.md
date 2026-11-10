# Deploying to IBM Cloud

## What you need

* An IBM Cloud account and an API key (IAM, access to Code Engine, Databases and Object Storage).
* `terraform` 1.5 or newer, the `ibmcloud` CLI with the `code-engine` plugin.
* The images pushed somewhere Code Engine can pull from. The `Images` workflow pushes them to GitHub Container Registry as `ghcr.io/<owner>/stock-<name>`. Make the packages public, or give Terraform a token (`image_registry_username` and `image_registry_password`).

## Steps

1. Push to `main`. CI runs the tests, then the `Images` workflow publishes 12 images.
2. Copy `infra/terraform/terraform.tfvars.example` to `terraform.tfvars` and adjust it.
3. `export TF_VAR_ibmcloud_api_key=...`
4. `scripts/deploy.sh`. It runs Terraform, runs the `db-init` job (schema, roles, sample data), runs the ingestor once, then the smoke test, and prints the UI address.

The managed PostgreSQL, Redis and RabbitMQ instances take 15 to 30 minutes to create the first time.

To deploy from GitHub instead, add the secrets listed at the top of `.github/workflows/deploy.yml` and run the `Deploy` workflow. Terraform state is kept in an Object Storage bucket so repeated runs update the same deployment.

## Autoscaling

Every service is a Code Engine app with `scale_min_instances = 1`, `scale_max_instances = max_instances` (5) and a target of 10 concurrent requests per copy. Change it with `terraform apply -var max_instances=1`. `loadtests/README.md` shows how to compare 1 copy with 5.

## Without managed data services

Set `data_mode = "external"` and give `external_database_admin_url`, `external_redis_url` and `external_amqp_url`, for example for a VM running the data containers from `docker-compose.yml`. This also keeps cost down while testing.

## Taking it down

`scripts/teardown.sh` runs `terraform destroy`. Do this after the demo; managed databases bill by the hour.

## Not verified yet

Docker and Terraform were not available where this was written. The Terraform files were checked with a parser and a reference checker (`scripts/check_terraform.py`) and CI runs `terraform validate`, but the first real `apply` may need small fixes to resource arguments, for example the memory and disk sizes the database plans accept in your region.
