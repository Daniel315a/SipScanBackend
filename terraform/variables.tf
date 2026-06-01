variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "sipscanback"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "Nombre del cluster GKE"
  type        = string
  default     = "sipscan-cluster"
}

variable "gar_repo_name" {
  description = "Nombre del repositorio en Artifact Registry"
  type        = string
  default     = "sipscan"
}

variable "node_machine_type" {
  description = "Tipo de máquina para los nodos del cluster"
  type        = string
  default     = "e2-medium"
}

variable "node_disk_size_gb" {
  description = "Tamaño del disco de cada nodo en GB"
  type        = number
  default     = 20
}

variable "node_count" {
  description = "Número inicial de nodos por zona"
  type        = number
  default     = 1
}

variable "min_node_count" {
  description = "Mínimo de nodos para el autoscaling"
  type        = number
  default     = 1
}

variable "max_node_count" {
  description = "Máximo de nodos para el autoscaling"
  type        = number
  default     = 3
}

variable "bastion_zone" {
  description = "Zona GCP para el bastion host"
  type        = string
  default     = "us-central1-a"
}

variable "bastion_machine_type" {
  description = "Tipo de máquina para el bastion host"
  type        = string
  default     = "e2-micro"
}

variable "bastion_iap_members" {
  description = "Usuarios/grupos con acceso SSH via IAP al bastion (ej: ['user:admin@example.com'])"
  type        = list(string)
  default     = []
}
