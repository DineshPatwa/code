# 🚢 Deploy PracticeOps to k3s (images built by Cloud Build)

This runs the whole app in your **self-managed k3s** cluster:

```
              k3s cluster (namespace: practiceops)
  http://SERVER_IP        →  Service(LoadBalancer :80)  → web pod   (nginx + static site)
  http://SERVER_IP:30081  →  Service(NodePort 30081)    → ttyd pod  (Ubuntu shell, basic auth)
```

No SSH tunnel, no VM stop/start dance. The lab page's terminal auto-connects to the
in-cluster ttyd pod.

---

## Fill these in first

| Placeholder | Meaning | Example |
|---|---|---|
| `PROJECT_ID` | Your GCP project id | `my-gcp-project` |
| `REGION` | Artifact Registry region | `us-central1` |
| `SERVER_IP` | Your k3s server's public IP | `34.13.70.29` |
| `STRONG_PASSWORD` | ttyd basic-auth password | (pick a strong one) |

Then edit two things in the repo:
1. **`js/config.js`** → set `terminalUrl: "http://SERVER_IP:30081"` (real IP).
2. **`k8s/web-deployment.yaml`** and **`k8s/terminal-deployment.yaml`** → replace
   `REGION` and `PROJECT_ID` in the `image:` lines. (Quick way on the server:
   `sed -i "s/REGION/us-central1/g; s/PROJECT_ID/my-gcp-project/g" k8s/*.yaml`)

---

## 1. Build & push the images (Cloud Build — no local Docker)

From the project folder, on any machine with `gcloud`:

```bash
# one-time: create the Artifact Registry repo
gcloud artifacts repositories create practiceops \
  --repository-format=docker --location=REGION

# build both images and push them
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION=REGION,_REPO=practiceops,_TAG=v1
```

> ℹ️ `js/config.js` is baked into the **web** image, so set your `SERVER_IP` there
> *before* this build.

Resulting images:
- `REGION-docker.pkg.dev/PROJECT_ID/practiceops/practiceops-web:v1`
- `REGION-docker.pkg.dev/PROJECT_ID/practiceops/practiceops-terminal:v1`

---

## 2. Let k3s pull from Artifact Registry (run on the k3s server)

Create a GCP service account with **Artifact Registry Reader**, download its JSON key
as `key.json`, then:

```bash
kubectl create namespace practiceops

kubectl -n practiceops create secret docker-registry gar-secret \
  --docker-server=REGION-docker.pkg.dev \
  --docker-username=_json_key \
  --docker-password="$(cat key.json)" \
  --docker-email=you@example.com
```

> Keep `key.json` off the server long-term / out of git. Delete it after.

---

## 3. Create the terminal credentials secret

```bash
kubectl -n practiceops create secret generic ttyd-auth \
  --from-literal=TTYD_USER=admin \
  --from-literal=TTYD_PASS='STRONG_PASSWORD'
```

(The ttyd container refuses to start without these — no unauthenticated shell.)

---

## 4. Deploy

```bash
kubectl apply -f k8s/
kubectl -n practiceops get pods,svc
```

Wait until both pods are `Running`. Then:

- **Site:** open `http://SERVER_IP`
- **Terminal:** open a lab → **💻 Open terminal** → it targets `http://SERVER_IP:30081`
  → browser asks for the basic-auth user/pass → live shell 🎉

---

## 5. Lock it down (do this before leaving it up)

The ttyd pod is a **root-capable shell on the network over plain HTTP** (password is
sniffable). At minimum, restrict access in your server/cloud firewall:

```bash
# allow only YOUR ip to the web + terminal ports; block the rest
# (example with ufw on the k3s node)
sudo ufw allow from YOUR_IP to any port 80
sudo ufw allow from YOUR_IP to any port 30081
```

**Recommended next step:** put it behind TLS (a domain + cert-manager, or a reverse proxy
with a self-signed cert) so credentials and traffic are encrypted. Until then, keep it
firewalled to your IP only.

---

## Redeploy after a change

```bash
# rebuild with a new tag
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION=REGION,_REPO=practiceops,_TAG=v2

# roll the deployments to the new tag
kubectl -n practiceops set image deploy/web \
  web=REGION-docker.pkg.dev/PROJECT_ID/practiceops/practiceops-web:v2
kubectl -n practiceops set image deploy/terminal \
  terminal=REGION-docker.pkg.dev/PROJECT_ID/practiceops/practiceops-terminal:v2

kubectl -n practiceops rollout status deploy/web
kubectl -n practiceops rollout status deploy/terminal
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Pod stuck `ImagePullBackOff` | `gar-secret` wrong/missing, or image tag/region/project mismatch. `kubectl -n practiceops describe pod POD`. |
| `terminal` pod `CrashLoopBackOff` | `ttyd-auth` secret missing → the entrypoint exits on purpose. Create it (step 3). |
| Site not reachable at `http://SERVER_IP` | Is the `web` Service `LoadBalancer` showing an external IP? `kubectl -n practiceops get svc`. On k3s, klipper needs host port 80 free. |
| Terminal panel blank | Firewall blocking `30081`, or `js/config.js` still has `SERVER_IP` placeholder (rebuild web image after editing). |
| Terminal loads but no basic-auth prompt / can't type | Image built without `-W`, or creds not injected — re-check the entrypoint & secret. |
| Want it over HTTPS | Add a domain + cert-manager (Traefik ingress) — the terminal must also be HTTPS to avoid mixed content. |

---

## Verify (end-to-end)

```bash
kubectl apply -f k8s/ --dry-run=client   # 1. manifests parse
kubectl -n practiceops get pods          # 2. web + terminal Running
curl -I http://SERVER_IP                 # 3. 200 OK
# 4. open a lab → Open terminal → log in → run: whoami / kubectl version --client / ls
```
