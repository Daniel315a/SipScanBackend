variable "project_id" {
  description = "GCP project ID (usado para Workload Identity pool)"
  type        = string
}

variable "region" {
  description = "Región donde se despliega el cluster"
  type        = string
}

variable "cluster_name" {
  description = "Nombre del cluster GKE"
  type        = string
}

variable "node_service_account" {
  description = "Email de la service account para los nodos (output del módulo iam)"
  type        = string
}

variable "node_machine_type" {
  description = "Tipo de máquina de los nodos"
  type        = string
  default     = "e2-medium"
}

variable "node_disk_size_gb" {
  description = "Tamaño del disco de cada nodo en GB"
  type        = number
  default     = 20
}

variable "node_count" {
  description = "Número inicial de nodos"
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
