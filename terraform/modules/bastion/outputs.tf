output "instance_name" {
  description = "Nombre de la instancia bastion"
  value       = google_compute_instance.bastion.name
}

output "zone" {
  description = "Zona del bastion"
  value       = google_compute_instance.bastion.zone
}

output "ssh_command" {
  description = "Comando para conectarse al bastion via IAP"
  value       = "gcloud compute ssh ${google_compute_instance.bastion.name} --tunnel-through-iap --zone=${google_compute_instance.bastion.zone} --project=${var.project_id}"
}

output "postgres_tunnel_command" {
  description = "Comando para crear tunnel SSH al PostgreSQL via bastion (reemplazar NODE_IP con la IP de un nodo GKE)"
  value       = "gcloud compute ssh ${google_compute_instance.bastion.name} --tunnel-through-iap --zone=${google_compute_instance.bastion.zone} --project=${var.project_id} -- -L 5432:NODE_IP:30432"
}
