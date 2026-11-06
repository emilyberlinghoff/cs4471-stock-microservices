import os
import time
import threading
import requests

# Use environment variable if provided, otherwise default to host.docker.internal or localhost
REGISTRY_HOST = os.getenv("REGISTRY_HOST", "host.docker.internal")

REGISTRIES = [
    f"http://{REGISTRY_HOST}:5000",
    f"http://{REGISTRY_HOST}:5002",
]
active_index = 0

def get_active_registry():
    global active_index
    return REGISTRIES[active_index]

def switch_registry():
    global active_index
    active_index = (active_index + 1) % len(REGISTRIES)
    print(f"[FAILOVER] Switched to registry: {REGISTRIES[active_index]}")

def register_service(service_id, name, url):
    payload = {"service_id": service_id, "name": name, "url": url}
    for _ in range(len(REGISTRIES)):
        target = get_active_registry()
        try:
            res = requests.post(f"{target}/register", json=payload, timeout=2)
            if res.status_code == 200:
                print(f"[REGISTRY] Registered {name} successfully on {target}")
                return True
        except requests.exceptions.RequestException:
            switch_registry()
    print("[ERROR] All registries unreachable.")
    return False

def _heartbeat_loop(service_id):
    while True:
        target = get_active_registry()
        try:
            requests.post(f"{target}/heartbeat", json={"service_id": service_id}, timeout=2)
        except requests.exceptions.RequestException:
            switch_registry()
        time.sleep(3)

def start_heartbeat(service_id):
    threading.Thread(target=_heartbeat_loop, args=(service_id,), daemon=True).start()