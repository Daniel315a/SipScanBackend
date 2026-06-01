output "name" {
  description = "Nombre del repositorio (usado en bindings IAM)"
  value       = google_artifact_registry_repository.this.name
}

output "uri" {
  description = "URI base para taggear y pushear imágenes"
  value       = "${var.location}-docker.pkg.dev/${google_artifact_registry_repository.this.project}/${var.repository_id}"
}
