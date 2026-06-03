output "cluster_name" {
  description = "Nombre del cluster GKE"
  value       = module.gke.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint del cluster GKE"
  value       = module.gke.cluster_endpoint
  sensitive   = true
}

output "artifact_registry_uri" {
  description = "URI base del repositorio (para docker tag/push)"
  value       = "${module.registry.uri}/sipscan"
}

output "kubectl_config_command" {
  description = "Comando para configurar kubectl con este cluster"
  value       = "gcloud container clusters get-credentials ${var.cluster_name} --region ${var.region} --project ${var.project_id}"
}

output "gke_nodes_service_account" {
  description = "Email de la service account de los nodos GKE"
  value       = module.iam.gke_nodes_email
}

output "bastion_ssh_command" {
  description = "Comando para conectarse al bastion via IAP"
  value       = module.bastion.ssh_command
}

output "bastion_postgres_tunnel" {
  description = "Comando para crear tunnel SSH al PostgreSQL (reemplazar NODE_IP)"
  value       = module.bastion.postgres_tunnel_command
}
