# S5 service registration and shutdown

Verified against source extracted read-only from the public `aashkaaa/stock-registry:latest` image on November 11, 2026 (application layer sha256:501627b42b87019f45d0c49260220a5ebbf4ec177170b3421f3548894695a716).

Configure `REGISTRY_URLS` as comma-separated base URLs and `SERVICE_PUBLIC_URL` as this service's externally reachable base URL. With no registry URLs, the API remains independently runnable and no registration thread starts. On startup, registration runs in the background. Both primary and backup receive full registration records. Heartbeats renew every three seconds; unknown-node 404 responses trigger re-registration, and unavailable registries are retried on later cycles without stopping the service.

```sh
export REGISTRY_URLS='http://localhost:5000,http://localhost:5002'
export SERVICE_PUBLIC_URL='http://localhost:5005'
python s5_server.py
```

Use this runner for graceful Control+C/SIGTERM handling. `GET /service-info` publishes service ID, name, description, and URL. When using Flask CLI, atexit cleanup handles normal interpreter exit; use the runner or deployment hooks for SIGTERM. Production WSGI workers need lifecycle ownership coordinated at deployment (avoid independent workers sharing one lease ID).

## Removal contract and limit

The verified registry has POST /register, POST /heartbeat, and GET /services. It has **no explicit deregistration endpoint**. Graceful shutdown stops heartbeats. The registry expires an inactive lease after 10 seconds, checked every 2 seconds: allow roughly 12 seconds after the last successful renewal. Registry scheduling can increase this delay. Other services continue renewing their leases. Abrupt process failure also uses expiry.

Do not claim immediate deregistration. `REGISTRY_REMOVE_PATH` can enable an explicitly agreed DELETE route containing `{service_id}`, but leave it unset for the current image. The existing registry also discards registration descriptions; completing discovery metadata requires its owner to retain that field. Immediate removal and returned descriptions remain registry-owner integration work.

Tests cover registration, backups, HTTP/transport failures, recovery, unknown-node re-registration, shutdown, and metadata. Service startup does not require provider access or a stock API key. Live cloud discovery is not claimed by local tests.
