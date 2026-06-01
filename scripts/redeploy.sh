#!/bin/bash
# Redeployment rápido: build -> push -> rollout
# Usar después del setup inicial para actualizaciones
set -e

cd "$(dirname "$0")/.."

GCP_PROJECT_ID="sipscanback"
GCP_REGION="us-central1"
GAR_REPO_NAME="sipscan"
NAMESPACE="sipscan"

GAR_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${GAR_REPO_NAME}/sipscan"
IMAGE_TAG=$(git rev-parse --short HEAD)

echo ">>> Construyendo imagen: ${GAR_URI}:${IMAGE_TAG}"

gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

docker build -t "sipscan:${IMAGE_TAG}" .
docker tag "sipscan:${IMAGE_TAG}" "${GAR_URI}:${IMAGE_TAG}"
docker tag "sipscan:${IMAGE_TAG}" "${GAR_URI}:latest"
docker push "${GAR_URI}:${IMAGE_TAG}"
docker push "${GAR_URI}:latest"

echo ">>> Actualizando deployment..."
kubectl set image deployment/sipscan-api api="${GAR_URI}:${IMAGE_TAG}" -n "${NAMESPACE}"
kubectl rollout status deployment/sipscan-api -n "${NAMESPACE}"

echo ">>> Deploy completado: ${IMAGE_TAG}"
