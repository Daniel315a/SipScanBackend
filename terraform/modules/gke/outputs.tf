output "cluster_name" {
  description = "Nombre del cluster GKE"
  value       = google_container_cluster.this.name
}

output "cluster_endpoint" {
  description = "Endpoint del cluster GKE"
  value       = google_container_cluster.this.endpoint
  sensitive   = true
}
