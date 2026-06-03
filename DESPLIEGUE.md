# Despliegue SIPScan en GCP (canary 90/10)

Comandos útiles para **subir** y **bajar** toda la infraestructura, operarla y
probar la distribución de tráfico entre el track **estable** (rama `main`) y el
**canary** (rama `canary`).

> La infraestructura (`terraform/`, `k8s/`) **no se versiona** (está en `.gitignore`).
> En particular `k8s/secret.yaml` contiene credenciales y **no debe subirse a git**.

## Variables del entorno

| Clave | Valor |
|---|---|
| Proyecto GCP | `sipscanback` |
| Región | `us-central1` |
| Cluster GKE | `sipscan-cluster` |
| Artifact Registry | `us-central1-docker.pkg.dev/sipscanback/sipscan/sipscan` |
| Namespace | `sipscan` |
| Reparto canary | 10% (anotación `canary-weight` del Ingress) |

```bash
export GAR=us-central1-docker.pkg.dev/sipscanback/sipscan/sipscan
export NS=sipscan
```

---

## 1. Subir la infraestructura (desde cero)

### 1.1 Provisionar con Terraform (cluster, registry, IAM, bastion)
```bash
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan          # ~10-15 min (crea el cluster GKE regional)
cd ..
```

### 1.2 Conectar kubectl al cluster
```bash
gcloud container clusters get-credentials sipscan-cluster \
  --region us-central1 --project sipscanback
kubectl get nodes
```

### 1.3 Instalar el Ingress Controller (ingress-nginx)
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/cloud/deploy.yaml
# Esperar a que el controller esté listo:
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=180s
```

### 1.4 Construir y subir las imágenes (estable + canary)
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

# Estable (rama main)
git worktree add /tmp/sipscan-main main
docker build -t $GAR:stable-$(git -C /tmp/sipscan-main rev-parse --short HEAD) -t $GAR:stable /tmp/sipscan-main
docker push $GAR:stable --all-tags 2>/dev/null || docker push $GAR:stable
git worktree remove /tmp/sipscan-main --force

# Canary (rama actual)
docker build -t $GAR:canary-$(git rev-parse --short HEAD) -t $GAR:canary .
docker push $GAR:canary
```
> Ajusta el tag de imagen en `k8s/deployment-stable.yaml` y `k8s/deployment-canary.yaml`.

### 1.5 Desplegar la aplicación
```bash
kubectl apply -f k8s/namespace.yaml          # primero el namespace
kubectl apply -f k8s/                         # secret, configmap, postgres, deployments, services, ingress, hpa
kubectl rollout status deploy/sipscan-api-stable -n $NS
kubectl rollout status deploy/sipscan-api-canary -n $NS
```

### 1.6 Obtener la IP pública
```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}'; echo
```

---

## 2. Operación diaria

```bash
# Estado general
kubectl get pods,svc,ingress -n $NS
kubectl get hpa -n $NS

# Logs
kubectl logs -n $NS deploy/sipscan-api-canary -f
kubectl logs -n $NS deploy/sipscan-api-stable -f

# Redesplegar una nueva imagen canary
docker build -t $GAR:canary-$(git rev-parse --short HEAD) -t $GAR:canary .
docker push $GAR:canary-$(git rev-parse --short HEAD)
kubectl set image deploy/sipscan-api-canary api=$GAR:canary-$(git rev-parse --short HEAD) -n $NS
kubectl rollout status deploy/sipscan-api-canary -n $NS

# Cambiar el peso del canary (p. ej. a 25%)
kubectl annotate ingress sipscan-api-canary -n $NS \
  nginx.ingress.kubernetes.io/canary-weight="25" --overwrite

# Promover canary a estable (cuando la versión es buena): apunta el deploy estable a la imagen canary
kubectl set image deploy/sipscan-api-stable api=$GAR:canary -n $NS

# Escalar manualmente
kubectl scale deploy/sipscan-api-canary --replicas=2 -n $NS
```

---

## 3. Probar la distribución de tráfico

```bash
python3 tools/check_split.py --ip 34.172.32.213 -n 200
```
Muestra el conteo y porcentaje real de respuestas servidas por STABLE vs CANARY.

---

## 4. Bajar la infraestructura

### 4.1 Borrar la aplicación (mantiene el cluster)
```bash
kubectl delete -f k8s/ --ignore-not-found
```

### 4.2 Borrar el Ingress Controller
```bash
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/cloud/deploy.yaml --ignore-not-found
```

### 4.3 Destruir TODA la infraestructura de GCP (cluster, registry, bastion…)
```bash
cd terraform
terraform destroy          # confirma con 'yes'
cd ..
```
> `terraform destroy` elimina el cluster y deja de generar costos. El estado
> local (`terraform/terraform.tfstate`) queda vacío; el `.backup` conserva el
> último estado conocido.

---

## Notas

- El reparto 90/10 lo hace **ingress-nginx por peso de petición**, no por número
  de pods, así que el HPA puede escalar el estable sin alterar la proporción.
- Ambos `Ingress` (`sipscan-api` y `sipscan-api-canary`) son *catch-all* (sin
  `host`), por lo que el acceso es por la **IP** del LoadBalancer.
- `k8s/secret.yaml` no está en git: créalo a partir de tus credenciales reales
  antes del `kubectl apply` del paso 1.5.
