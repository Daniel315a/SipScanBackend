variable "sa_account_id" {
  description = "ID de la service account para los nodos GKE"
  type        = string
  default     = "sipscan-gke-nodes"
}

variable "sa_display_name" {
  description = "Nombre visible de la service account"
  type        = string
  default     = "SipScan GKE Nodes"
}

variable "registry_location" {
  description = "Región del repositorio Artifact Registry"
  type        = string
}

variable "registry_name" {
  description = "Nombre del repositorio Artifact Registry (output del módulo registry)"
  type        = string
}
