#!/bin/bash
# =============================================================================
# Setup completo: GKE + Artifact Registry + Deploy
# Requisitos: gcloud CLI, kubectl, docker
# =============================================================================
set -e

# Deshabilitar prompts interactivos de gcloud (survey, confirmaciones)
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
export CLOUDSDK_SURVEY_DISABLE=true

# --- CONFIGURACIÓN (edita estos valores) ---
GCP_PROJECT_ID="sipscan-493204"
GCP_REGION="us-central1"
CLUSTER_NAME="sipscan-cluster"
GAR_REPO_NAME="sipscan"
NAMESPACE="sipscan"
# ------------------------------------------

GAR_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${GAR_REPO_NAME}/sipscan"

echo ">>> Project: ${GCP_PROJECT_ID}"
echo ">>> Artifact Registry: ${GAR_URI}"

# =============================================================================
# PASO 1: Configurar gcloud y habilitar APIs
# =============================================================================
echo ""
echo "=== PASO 1: Configurando GCP ==="
gcloud config set project "${GCP_PROJECT_ID}"
gcloud services enable \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  --quiet

# =============================================================================
# PASO 2: Crear cluster GKE
# =============================================================================
echo ""
echo "=== PASO 2: Creando cluster GKE ==="
gcloud container clusters create "${CLUSTER_NAME}" \
  --region "${GCP_REGION}" \
  --num-nodes 1 \
  --machine-type e2-medium \
  --disk-size 20 \
  --enable-autoscaling \
  --min-nodes 1 \
  --max-nodes 3 \
  --workload-pool "${GCP_PROJECT_ID}.svc.id.goog" \
  --quiet

# Obtener credenciales para kubectl
gcloud container clusters get-credentials "${CLUSTER_NAME}" --region "${GCP_REGION}"
echo "Cluster GKE creado."

# =============================================================================
# PASO 3: Crear repositorio en Artifact Registry
# =============================================================================
echo ""
echo "=== PASO 3: Creando repositorio Artifact Registry ==="
gcloud artifacts repositories create "${GAR_REPO_NAME}" \
  --repository-format=docker \
  --location="${GCP_REGION}" \
  --description="SipScan backend images" \
  --quiet

gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet
echo "Repositorio creado: ${GAR_URI}"

# =============================================================================
# PASO 4: Construir y subir imagen Docker
# =============================================================================
echo ""
echo "=== PASO 4: Build y push de imagen Docker ==="
IMAGE_TAG=$(git rev-parse --short HEAD)

docker build -t "sipscan:${IMAGE_TAG}" .
docker tag "sipscan:${IMAGE_TAG}" "${GAR_URI}:${IMAGE_TAG}"
docker tag "sipscan:${IMAGE_TAG}" "${GAR_URI}:latest"
docker push "${GAR_URI}:${IMAGE_TAG}"
docker push "${GAR_URI}:latest"
echo "Imagen publicada: ${GAR_URI}:${IMAGE_TAG}"

# =============================================================================
# PASO 5: Actualizar manifiestos con valores reales
# =============================================================================
echo ""
echo "=== PASO 5: Actualizando manifiestos ==="
sed -i "s|us-central1-docker.pkg.dev/PROJECT_ID/sipscan/sipscan:latest|${GAR_URI}:${IMAGE_TAG}|g" \
  k8s/deployment.yaml
echo "Manifiesto de deployment actualizado."

# =============================================================================
# PASO 6: Instalar metrics-server (para HPA)
# =============================================================================
echo ""
echo "=== PASO 6: Instalando metrics-server ==="
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# =============================================================================
# PASO 7: Aplicar manifiestos de Kubernetes
# =============================================================================
echo ""
echo "=== PASO 7: Aplicando manifiestos en Kubernetes ==="
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
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# =============================================================================
# PASO 8: Obtener IP del LoadBalancer
# =============================================================================
echo ""
echo "=== PASO 8: Esperando LoadBalancer (1-2 min) ==="
sleep 30

for i in $(seq 1 12); do
  IP=$(kubectl get service sipscan-api -n "${NAMESPACE}" \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
  if [ -n "${IP}" ]; then
    echo ""
    echo "=== DESPLIEGUE COMPLETADO ==="
    echo "IP pública: ${IP}"
    echo "API:        http://${IP}/docs"
    break
  fi
  echo "Esperando IP... (${i}/12)"
  sleep 10
done
