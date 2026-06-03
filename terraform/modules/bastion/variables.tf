variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "zone" {
  description = "GCP zone para el bastion host"
  type        = string
}

variable "machine_type" {
  description = "Tipo de máquina para el bastion"
  type        = string
  default     = "e2-micro"
}

variable "network" {
  description = "VPC network donde se despliega el bastion"
  type        = string
  default     = "default"
}

variable "iap_members" {
  description = "Lista de usuarios/grupos con acceso SSH via IAP (ej: ['user:admin@example.com'])"
  type        = list(string)
  default     = []
}
