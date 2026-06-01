#!/bin/bash
# =============================================================================
# Deploy inicial de la aplicación en un cluster GKE ya provisionado con Terraform.
# Requisitos: gcloud CLI, kubectl, docker
# La infraestructura (GKE + Artifact Registry) se gestiona en terraform/
# =============================================================================
set -e

cd "$(dirname "$0")/.."

export CLOUDSDK_CORE_DISABLE_PROMPTS=1
export CLOUDSDK_SURVEY_DISABLE=true

GCP_PROJECT_ID="sipscanback"
GCP_REGION="us-central1"
CLUSTER_NAME="sipscan-cluster"
GAR_REPO_NAME="sipscan"
NAMESPACE="sipscan"

GAR_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${GAR_REPO_NAME}/sipscan"

echo ">>> Project:           ${GCP_PROJECT_ID}"
echo ">>> Artifact Registry: ${GAR_URI}"
echo ""
echo "NOTA: Este script asume que el cluster GKE y el repositorio Artifact Registry"
echo "      ya fueron creados con Terraform (ver terraform/)."
echo ""

# =============================================================================
# PASO 1: Obtener credenciales del cluster
# =============================================================================
echo "=== PASO 1: Configurando kubectl ==="
gcloud config set project "${GCP_PROJECT_ID}"
gcloud container clusters get-credentials "${CLUSTER_NAME}" --region "${GCP_REGION}"

# =============================================================================
# PASO 2: Build y push de la imagen Docker
# =============================================================================
echo ""
echo "=== PASO 2: Build y push de imagen Docker ==="
IMAGE_TAG=$(git rev-parse --short HEAD)

gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

docker build -t "sipscan:${IMAGE_TAG}" .
docker tag "sipscan:${IMAGE_TAG}" "${GAR_URI}:${IMAGE_TAG}"
docker tag "sipscan:${IMAGE_TAG}" "${GAR_URI}:latest"
docker push "${GAR_URI}:${IMAGE_TAG}"
docker push "${GAR_URI}:latest"
echo "Imagen publicada: ${GAR_URI}:${IMAGE_TAG}"

# =============================================================================
# PASO 3: Actualizar tag de imagen en el deployment
# =============================================================================
echo ""
echo "=== PASO 3: Actualizando manifiestos ==="
sed -i "s|us-central1-docker.pkg.dev/sipscanback/sipscan/sipscan:.*|${GAR_URI}:${IMAGE_TAG}|g" \
  k8s/deployment.yaml
echo "Tag de imagen actualizado a: ${IMAGE_TAG}"

# =============================================================================
# PASO 4: Instalar metrics-server (para HPA)
# =============================================================================
echo ""
echo "=== PASO 4: Instalando metrics-server ==="
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# =============================================================================
# PASO 5: Aplicar manifiestos de Kubernetes
# =============================================================================
echo ""
echo "=== PASO 5: Aplicando manifiestos ==="
echo ""
echo "AVISO: Asegúrate de haber editado k8s/secret.yaml con tus valores reales."
echo "Presiona ENTER para continuar o Ctrl+C para cancelar."
read -r

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/postgres.yaml
echo "Esperando a que PostgreSQL esté listo..."
kubectl rollout status statefulset/postgres -n "${NAMESPACE}" --timeout=120s
kubectl apply -f k8s/postgres-nodeport.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# =============================================================================
# PASO 6: Desplegar stack de monitoreo (Grafana Alloy + Prometheus + Grafana)
# =============================================================================
echo ""
echo "=== PASO 6: Desplegando stack de monitoreo ==="
echo ""
echo "AVISO: Asegúrate de cambiar la contraseña de Grafana en k8s/monitoring/grafana.yaml"
echo "       (campo admin-password en el Secret grafana-secret) antes de continuar."
echo "Presiona ENTER para continuar o Ctrl+C para cancelar."
read -r

kubectl apply -f k8s/monitoring/namespace.yaml
kubectl apply -f k8s/monitoring/rbac.yaml
kubectl apply -f k8s/monitoring/prometheus.yaml
kubectl apply -f k8s/monitoring/grafana-alloy-config.yaml
kubectl apply -f k8s/monitoring/grafana-alloy.yaml
kubectl apply -f k8s/monitoring/grafana.yaml

echo "Esperando a que Prometheus esté listo (puede tardar ~2 min mientras provisiona el disco)..."
kubectl rollout status statefulset/prometheus -n monitoring --timeout=300s
echo "Esperando a que Grafana esté lista..."
kubectl rollout status deployment/grafana -n monitoring --timeout=180s

# =============================================================================
# PASO 7: Obtener IPs de los LoadBalancers
# =============================================================================
echo ""
echo "=== PASO 7: Esperando LoadBalancers (1-2 min) ==="
sleep 30

for i in $(seq 1 12); do
  IP=$(kubectl get service sipscan-api -n "${NAMESPACE}" \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
  if [ -n "${IP}" ]; then
    echo ""
    echo "=== DESPLIEGUE COMPLETADO ==="
    echo "IP pública API: ${IP}"
    echo "API:            http://${IP}/docs"
    break
  fi
  echo "Esperando IP de la API... (${i}/12)"
  sleep 10
done

GRAFANA_IP=""
for i in $(seq 1 12); do
  GRAFANA_IP=$(kubectl get service grafana -n monitoring \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
  if [ -n "${GRAFANA_IP}" ]; then
    echo "Grafana:        http://${GRAFANA_IP} (admin / ver grafana-secret)"
    break
  fi
  echo "Esperando IP de Grafana... (${i}/12)"
  sleep 10
done

NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null)
echo ""
echo "=== ACCESO A POSTGRESQL VIA BASTION ==="
echo "Nodo GKE (InternalIP): ${NODE_IP}"
echo "Tunnel SSH:"
echo "  gcloud compute ssh sipscan-bastion --tunnel-through-iap --zone=us-central1-a \\"
echo "    -- -L 5432:${NODE_IP}:30432"
echo "  psql -h localhost -p 5432 -U sipscan_user -d sipscan"
