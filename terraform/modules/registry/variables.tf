variable "location" {
  description = "Región donde se crea el repositorio"
  type        = string
}

variable "repository_id" {
  description = "ID del repositorio en Artifact Registry"
  type        = string
}

variable "description" {
  description = "Descripción del repositorio"
  type        = string
  default     = "Docker image repository"
}
