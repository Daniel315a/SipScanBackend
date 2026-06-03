output "gke_nodes_email" {
  description = "Email de la service account de los nodos GKE"
  value       = google_service_account.gke_nodes.email
}

output "gke_nodes_id" {
  description = "ID único de la service account"
  value       = google_service_account.gke_nodes.id
}
