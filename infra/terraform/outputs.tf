output "ui_url" {
  description = "Open this in a browser."
  value       = ibm_code_engine_app.ui.endpoint
}

output "registry_primary_url" {
  value = ibm_code_engine_app.registry_primary.endpoint
}

output "registry_backup_url" {
  value = ibm_code_engine_app.registry_backup.endpoint
}

output "service_urls" {
  value = { for name, app in ibm_code_engine_app.service : name => app.endpoint }
}

output "project_name" {
  description = "Code Engine project, for ibmcloud ce commands."
  value       = ibm_code_engine_project.project.name
}

output "registry_key" {
  value     = local.registry_key
  sensitive = true
}
