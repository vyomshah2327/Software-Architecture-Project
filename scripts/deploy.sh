#!/usr/bin/env bash
# Deploy the platform to IBM Cloud Code Engine.
#   export TF_VAR_ibmcloud_api_key=...      (never put the key in a file)
#   cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   and edit it
#   scripts/deploy.sh
# Needs: terraform, the ibmcloud CLI with the code-engine plugin, images already pushed (see build_images.sh or CI).
set -euo pipefail
cd "$(dirname "$0")/.."
TF=infra/terraform
: "${TF_VAR_ibmcloud_api_key:?set TF_VAR_ibmcloud_api_key}"

terraform -chdir=$TF init -input=false
terraform -chdir=$TF apply -input=false -auto-approve

REGION=$(terraform -chdir=$TF console <<<'var.region' | tr -d '"')
PROJECT=$(terraform -chdir=$TF output -raw project_name)
UI=$(terraform -chdir=$TF output -raw ui_url)
PRIMARY=$(terraform -chdir=$TF output -raw registry_primary_url)
BACKUP=$(terraform -chdir=$TF output -raw registry_backup_url)

ibmcloud login --apikey "$TF_VAR_ibmcloud_api_key" -r "$REGION" -q >/dev/null
ibmcloud ce project select --name "$PROJECT" -q

echo "Creating the schema, roles and sample data"
ibmcloud ce jobrun submit --job db-init --name "db-init-$(date +%s)" --wait --wait-timeout 300

echo "Loading the first prices"
ibmcloud ce jobrun submit --job market-data-ingestor --name "ingest-$(date +%s)" --wait --wait-timeout 900

echo "Checking the deployment"
scripts/smoke_test.sh "$UI" "$PRIMARY" "$BACKUP"
echo
echo "Open: $UI"
