terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Descomentar para guardar el estado en GCS (recomendado en producción):
  # backend "gcs" {
  #   bucket = "sipscanback-terraform-state"
  #   prefix = "sipscan/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "container" {
  service            = "container.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "compute" {
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iap" {
  service            = "iap.googleapis.com"
  disable_on_destroy = false
}

module "registry" {
  source = "./modules/registry"

  location      = var.region
  repository_id = var.gar_repo_name
  description   = "SipScan backend Docker images"

  depends_on = [google_project_service.artifactregistry]
}

module "iam" {
  source = "./modules/iam"

  registry_location = var.region
  registry_name     = module.registry.name
}

module "bastion" {
  source = "./modules/bastion"

  project_id   = var.project_id
  zone         = var.bastion_zone
  machine_type = var.bastion_machine_type
  iap_members  = var.bastion_iap_members

  depends_on = [
    google_project_service.compute,
    google_project_service.iap,
  ]
}

module "gke" {
  source = "./modules/gke"

  project_id           = var.project_id
  region               = var.region
  cluster_name         = var.cluster_name
  node_service_account = module.iam.gke_nodes_email
  node_machine_type    = var.node_machine_type
  node_disk_size_gb    = var.node_disk_size_gb
  node_count           = var.node_count
  min_node_count       = var.min_node_count
  max_node_count       = var.max_node_count

  depends_on = [google_project_service.container]
}
