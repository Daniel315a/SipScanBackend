# Despliegue SIPScan en GCP

Comandos útiles para **subir** y **bajar** toda la infraestructura y operarla.
La API se despliega como un **único track** a partir de la rama `main`.

> Los manifiestos de `k8s/` **sí se versionan**, salvo `k8s/secret.yaml`, que
> contiene credenciales reales y está en `.gitignore` (**no debe subirse a git**;
> usa `k8s/secret.example.yaml` como plantilla). `terraform/` tampoco se versiona.

## Variables del entorno

| Clave | Valor |
|---|---|
| Proyecto GCP | `sipscanback` |
| Región | `us-central1` |
| Cluster GKE | `sipscan-cluster` |
| Artifact Registry | `us-central1-docker.pkg.dev/sipscanback/sipscan/sipscan` |
| Namespace | `sipscan` |

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

### 1.4 Construir y subir la imagen (desde main)
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

git worktree add /tmp/sipscan-main main
docker build -t $GAR:$(git -C /tmp/sipscan-main rev-parse --short HEAD) -t $GAR:latest /tmp/sipscan-main
docker push $GAR:latest --all-tags 2>/dev/null || docker push $GAR:latest
git worktree remove /tmp/sipscan-main --force
```
> Ajusta el tag de imagen en `k8s/deployment.yaml` si fijas un commit concreto.

### 1.5 Desplegar la aplicación
```bash
kubectl apply -f k8s/namespace.yaml          # primero el namespace
kubectl apply -f k8s/                         # secret, configmap, postgres, deployment, service, ingress, hpa
kubectl rollout status deploy/sipscan-api -n $NS
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
kubectl logs -n $NS deploy/sipscan-api -f

# Redesplegar una nueva imagen (desde main)
docker build -t $GAR:$(git rev-parse --short HEAD) -t $GAR:latest .
docker push $GAR:$(git rev-parse --short HEAD)
docker push $GAR:latest
kubectl set image deploy/sipscan-api api=$GAR:$(git rev-parse --short HEAD) -n $NS
kubectl rollout status deploy/sipscan-api -n $NS

# Revertir al despliegue anterior si algo falla
kubectl rollout undo deploy/sipscan-api -n $NS

# Escalar manualmente
kubectl scale deploy/sipscan-api --replicas=3 -n $NS
```

---

## 3. Comprobar el estado de la API

```bash
IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl -s http://$IP/health | jq
```
Devuelve `{"status":"ok","version":"...","deploy_date":"..."}`.

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

- El `Ingress` (`sipscan-api`) es *catch-all* (sin `host`), por lo que el acceso
  es por la **IP** del LoadBalancer del controller ingress-nginx.
- El despliegue es un **único track** desde `main`. Para introducir cambios de
  forma gradual usa `kubectl rollout` (rolling update) y, si hace falta volver
  atrás, `kubectl rollout undo`.
- `k8s/secret.yaml` no está en git: créalo a partir de `k8s/secret.example.yaml`
  con tus credenciales reales antes del `kubectl apply` del paso 1.5.
