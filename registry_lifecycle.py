"""Lease-based lifecycle for the verified aashkaaa/stock-registry API.

The published image has POST /register, POST /heartbeat, GET /services and a
10-second lease pruned every 2 seconds. It has no explicit delete endpoint.
"""

import atexit
import logging
import os
import threading
from urllib.parse import quote, urlparse

import requests


class RegistryLifecycle:
    def __init__(self, metadata, urls, *, session=None, interval=3, timeout=2, remove_path=None):
        if not urls or any(urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc for url in urls):
            raise ValueError("Registry URLs must be absolute HTTP(S) URLs.")
        if not 0 < interval <= 3 or not 0 < timeout <= 2:
            raise ValueError("Heartbeat interval must be at most 3 seconds and timeout at most 2 seconds.")
        if remove_path and (not remove_path.startswith("/") or "{service_id}" not in remove_path):
            raise ValueError("Removal path must start with / and contain {service_id}.")
        self.metadata = dict(metadata)
        self.urls = list(dict.fromkeys(url.rstrip("/") for url in urls))
        self.session = session if session is not None else requests
        self.interval, self.timeout, self.remove_path = interval, timeout, remove_path
        self.registered = {url: False for url in self.urls}
        self._stop = threading.Event()
        self._thread = None
        self._logger = logging.getLogger(__name__)

    @classmethod
    def from_environment(cls, metadata):
        urls = [value.strip() for value in os.getenv("REGISTRY_URLS", "").split(",") if value.strip()]
        return cls(metadata, urls, remove_path=os.getenv("REGISTRY_REMOVE_PATH") or None) if urls else None

    def _post(self, url, path, payload):
        try:
            response = self.session.post(url + path, json=payload, timeout=self.timeout, allow_redirects=False)
            try:
                return response.status_code
            finally:
                response.close()
        except requests.RequestException:
            return None

    def renew_once(self):
        """Maintain each configured registry independently, including backups."""
        for url in self.urls:
            if self._stop.is_set():
                break
            if self.registered[url]:
                status = self._post(url, "/heartbeat", {"service_id": self.metadata["service_id"]})
                self.registered[url] = status == 200
                if status != 404:
                    continue
            # A restarted/backup registry may not know this service yet.
            self.registered[url] = self._post(url, "/register", self.metadata) == 200

    def _run(self):
        while not self._stop.is_set():
            self.renew_once()
            self._stop.wait(self.interval)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="registry-lease", daemon=True)
        self._thread.start()
        atexit.register(self.stop)

    def stop(self):
        if self._stop.is_set():
            return
        self._stop.set()
        if self._thread and threading.current_thread() is not self._thread:
            self._thread.join(timeout=len(self.urls) * self.timeout * 2 + 1)
        if self.remove_path:
            path = self.remove_path.replace("{service_id}", quote(self.metadata["service_id"], safe=""))
            for url in self.urls:
                try:
                    response = self.session.delete(url + path, timeout=self.timeout, allow_redirects=False)
                    response.close()
                except requests.RequestException:
                    pass  # Ceasing heartbeats still permits lease expiry.
        self.registered = {url: False for url in self.urls}


def service_metadata(service_id, name, description, endpoint, port):
    base = os.getenv("SERVICE_PUBLIC_URL", f"http://localhost:{port}").rstrip("/")
    if urlparse(base).scheme not in ("http", "https") or not urlparse(base).netloc:
        raise ValueError("SERVICE_PUBLIC_URL must be an absolute HTTP(S) base URL.")
    return {"service_id": service_id, "name": name, "description": description, "url": base + endpoint}
