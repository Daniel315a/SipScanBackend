resource "google_compute_instance" "bastion" {
  name         = "sipscan-bastion"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["bastion"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
    }
  }

  # Sin IP pública: acceso exclusivo via IAP SSH tunnel
  network_interface {
    network = var.network
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  # Startup script: instala herramientas necesarias para debug de DB
  metadata_startup_script = <<-EOT
    #!/bin/bash
    apt-get update -q
    apt-get install -y -q postgresql-client netcat-openbsd
  EOT

  service_account {
    scopes = ["cloud-platform"]
  }
}

# Permite que IAP (35.235.240.0/20) haga SSH al bastion
resource "google_compute_firewall" "iap_ssh_bastion" {
  name    = "sipscan-allow-iap-ssh-bastion"
  network = var.network

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["bastion"]
}

# Permite al bastion alcanzar los nodos GKE en el rango de NodePorts
resource "google_compute_firewall" "bastion_to_gke_nodeport" {
  name    = "sipscan-allow-bastion-to-gke-nodeport"
  network = var.network

  allow {
    protocol = "tcp"
    ports    = ["30000-32767"]
  }

  source_tags = ["bastion"]
  target_tags = ["gke-sipscan-node"]
}

# IAM: otorga acceso IAP SSH a los miembros configurados
resource "google_iap_tunnel_instance_iam_binding" "ssh_access" {
  count = length(var.iap_members) > 0 ? 1 : 0

  project  = var.project_id
  zone     = var.zone
  instance = google_compute_instance.bastion.name
  role     = "roles/iap.tunnelResourceAccessor"
  members  = var.iap_members
}
