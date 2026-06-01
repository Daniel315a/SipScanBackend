resource "google_service_account" "gke_nodes" {
  account_id   = var.sa_account_id
  display_name = var.sa_display_name
}

resource "google_artifact_registry_repository_iam_member" "nodes_reader" {
  location   = var.registry_location
  repository = var.registry_name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.gke_nodes.email}"
}
