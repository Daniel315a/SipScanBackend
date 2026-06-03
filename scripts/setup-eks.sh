#!/bin/bash
# =============================================================================
# Setup completo: EKS + ECR + IRSA + Deploy
# Requisitos: aws-cli, eksctl, kubectl, docker
# =============================================================================
set -e

# --- CONFIGURACIÓN ---
AWS_REGION="us-east-1"
CLUSTER_NAME="sipscan-cluster"
ECR_REPO_NAME="sipscan"
NAMESPACE="sipscan"
IAM_POLICY_NAME="SipScanApiPolicy"
IAM_ROLE_NAME="sipscan-api-role"
S3_BUCKET="tu-bucket-sipscan"  # Debe coincidir con iam/sipscan-policy.json
# ------------------------------------------

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo ">>> Account ID: ${ACCOUNT_ID}"
echo ">>> ECR URI: ${ECR_URI}"

# =============================================================================
# PASO 1: Crear cluster EKS
# =============================================================================
echo ""
echo "=== PASO 1: Creando cluster EKS ==="
eksctl create cluster -f eksctl-cluster.yaml
echo "Cluster creado."

# =============================================================================
# PASO 2: Crear repositorio ECR
# =============================================================================
echo ""
echo "=== PASO 2: Creando repositorio ECR ==="
aws ecr create-repository \
  --repository-name "${ECR_REPO_NAME}" \
  --region "${AWS_REGION}" \
  --image-scanning-configuration scanOnPush=true \
  --query "repository.repositoryUri" \
  --output text
echo "Repositorio ECR creado: ${ECR_URI}"

# =============================================================================
# PASO 3: Construir y subir imagen Docker
# =============================================================================
echo ""
echo "=== PASO 3: Build y push de imagen Docker ==="
IMAGE_TAG=$(git rev-parse --short HEAD)

aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker build -t "${ECR_REPO_NAME}:${IMAGE_TAG}" .
docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:latest"
docker push "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:latest"
echo "Imagen publicada: ${ECR_URI}:${IMAGE_TAG}"

# =============================================================================
# PASO 4: Crear política IAM y rol para IRSA
# =============================================================================
echo ""
echo "=== PASO 4: Creando política y rol IAM para IRSA ==="

# Actualizar el nombre del bucket en la policy
sed -i "s/tu-bucket-sipscan/${S3_BUCKET}/g" iam/sipscan-policy.json

POLICY_ARN=$(aws iam create-policy \
  --policy-name "${IAM_POLICY_NAME}" \
  --policy-document file://iam/sipscan-policy.json \
  --query "Policy.Arn" \
  --output text)
echo "Política creada: ${POLICY_ARN}"

OIDC_PROVIDER=$(aws eks describe-cluster \
  --name "${CLUSTER_NAME}" \
  --region "${AWS_REGION}" \
  --query "cluster.identity.oidc.issuer" \
  --output text | sed 's|https://||')

eksctl create iamserviceaccount \
  --cluster "${CLUSTER_NAME}" \
  --namespace "${NAMESPACE}" \
  --name "sipscan-api" \
  --attach-policy-arn "${POLICY_ARN}" \
  --role-name "${IAM_ROLE_NAME}" \
  --approve \
  --override-existing-serviceaccounts

echo "ServiceAccount con IRSA creado."

# Obtener el ARN del rol para actualizar el manifiesto
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${IAM_ROLE_NAME}"
echo "Role ARN: ${ROLE_ARN}"

# =============================================================================
# PASO 5: Actualizar manifiestos con valores reales
# =============================================================================
echo ""
echo "=== PASO 5: Actualizando manifiestos ==="

# Actualizar imagen en deployment
sed -i "s|ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/sipscan:latest|${ECR_URI}:${IMAGE_TAG}|g" \
  k8s/deployment.yaml

# Actualizar ACCOUNT_ID en serviceaccount
sed -i "s|ACCOUNT_ID|${ACCOUNT_ID}|g" k8s/serviceaccount.yaml

echo "Manifiestos actualizados."

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
echo "AVISO: Edita k8s/secret.yaml con tus valores reales antes de continuar."
echo "Presiona ENTER cuando hayas editado el secret, o Ctrl+C para cancelar."
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
# PASO 8: Obtener IP/hostname del LoadBalancer
# =============================================================================
echo ""
echo "=== PASO 8: Esperando LoadBalancer ==="
echo "Esto puede tomar 1-2 minutos..."
sleep 30

kubectl get service sipscan-api -n "${NAMESPACE}"
echo ""
echo "URL de la API:"
kubectl get service sipscan-api -n "${NAMESPACE}" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
echo ""
echo ""
echo "=== DESPLIEGUE COMPLETADO ==="
