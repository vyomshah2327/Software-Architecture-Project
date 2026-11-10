#!/usr/bin/env bash
# Remove everything Terraform created. Managed databases stop costing money once this finishes.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${TF_VAR_ibmcloud_api_key:?set TF_VAR_ibmcloud_api_key}"
read -r -p "This deletes the whole platform, including its databases. Type yes to continue: " answer
[ "$answer" = "yes" ] || { echo "cancelled"; exit 1; }
terraform -chdir=infra/terraform destroy -input=false -auto-approve
