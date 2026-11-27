#!/usr/bin/env python3
"""Ollama Prometheus exporter.

Polls the Ollama API and exposes metrics at /metrics on port 9110.
Collected from:
  - /api/tags  — model list and sizes
  - /api/ps    — currently loaded models (VRAM usage)
  - /api/version — Ollama version
"""

import os
import time
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from prometheus_client import (
    Gauge,
    Counter,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s ollama-exporter %(levelname)s %(message)s",
)
log = logging.getLogger("ollama-exporter")

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", "9110"))
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))

registry = CollectorRegistry()

# --- Availability ---
ollama_up = Gauge("ollama_up", "Ollama API availability (1=up, 0=down)", registry=registry)
ollama_api_latency = Histogram(
    "ollama_api_latency_seconds",
    "Ollama API response latency",
    ["endpoint"],
    registry=registry,
)

# --- Version ---
ollama_version_info = Info("ollama_version", "Ollama version info", registry=registry)

# --- Models ---
ollama_models_total = Gauge(
    "ollama_models_total",
    "Total number of models available in Ollama",
    registry=registry,
)
ollama_model_size_bytes = Gauge(
    "ollama_model_size_bytes",
    "Size of each model in bytes",
    ["model"],
    registry=registry,
)
ollama_model_parameter_size = Gauge(
    "ollama_model_parameter_size",
    "Parameter count of each model (in billions, parsed from details)",
    ["model"],
    registry=registry,
)

# --- Loaded models (VRAM) ---
ollama_loaded_models_total = Gauge(
    "ollama_loaded_models_total",
    "Number of models currently loaded in memory",
    registry=registry,
)
ollama_loaded_model_size_bytes = Gauge(
    "ollama_loaded_model_size_bytes",
    "Size in bytes of each currently loaded model",
    ["model"],
    registry=registry,
)
ollama_loaded_model_vram_bytes = Gauge(
    "ollama_loaded_model_vram_bytes",
    "VRAM used by each currently loaded model",
    ["model"],
    registry=registry,
)
ollama_loaded_model_expires_seconds = Gauge(
    "ollama_loaded_model_expires_seconds",
    "Seconds until loaded model is unloaded (TTL)",
    ["model"],
    registry=registry,
)

# --- Scrape health ---
ollama_scrape_errors = Counter(
    "ollama_scrape_errors_total",
    "Number of failed Ollama API scrapes",
    ["endpoint"],
    registry=registry,
)
ollama_last_scrape = Gauge(
    "ollama_last_scrape_timestamp_seconds",
    "Unix timestamp of the last successful scrape",
    registry=registry,
)


def _get(path: str, timeout: int = 10) -> tuple[dict | list | None, float]:
    url = f"{OLLAMA_URL}{path}"
    start = time.monotonic()
    try:
        r = requests.get(url, timeout=timeout)
        latency = time.monotonic() - start
        if r.status_code == 200:
            return r.json(), latency
        return None, latency
    except Exception as exc:
        latency = time.monotonic() - start
        log.warning("GET %s failed: %s", path, exc)
        return None, latency


def _parse_param_billions(size_str: str | None) -> float:
    """Parse '9B', '27B', '4.6B' → float billions."""
    if not size_str:
        return 0.0
    s = str(size_str).strip().upper()
    try:
        if s.endswith("B"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000.0
    except ValueError:
        pass
    return 0.0


def _scrape() -> bool:
    ok = False

    # /api/version
    data, lat = _get("/api/version")
    ollama_api_latency.labels(endpoint="/api/version").observe(lat)
    if data:
        ollama_version_info.info({"version": str(data.get("version", "unknown"))})
        ok = True
    else:
        ollama_scrape_errors.labels(endpoint="/api/version").inc()

    # /api/tags — model list
    data, lat = _get("/api/tags")
    ollama_api_latency.labels(endpoint="/api/tags").observe(lat)
    if data and isinstance(data.get("models"), list):
        models = data["models"]
        ollama_models_total.set(len(models))
        for m in models:
            name = str(m.get("name", "unknown"))
            size = int(m.get("size", 0))
            ollama_model_size_bytes.labels(model=name).set(size)
            param_b = _parse_param_billions(
                (m.get("details") or {}).get("parameter_size")
            )
            if param_b > 0:
                ollama_model_parameter_size.labels(model=name).set(param_b)
        ok = True
    else:
        ollama_scrape_errors.labels(endpoint="/api/tags").inc()

    # /api/ps — running models
    data, lat = _get("/api/ps")
    ollama_api_latency.labels(endpoint="/api/ps").observe(lat)
    if data is not None:
        models = data.get("models") or []
        ollama_loaded_models_total.set(len(models))
        for m in models:
            name = str(m.get("name", "unknown"))
            ollama_loaded_model_size_bytes.labels(model=name).set(int(m.get("size", 0)))
            ollama_loaded_model_vram_bytes.labels(model=name).set(
                int(m.get("size_vram", 0))
            )
            # expires_at is ISO8601 — compute delta from now
            expires_at = m.get("expires_at")
            if expires_at:
                try:
                    from datetime import datetime, timezone
                    exp = datetime.fromisoformat(
                        str(expires_at).replace("Z", "+00:00")
                    )
                    delta = (exp - datetime.now(timezone.utc)).total_seconds()
                    ollama_loaded_model_expires_seconds.labels(model=name).set(max(0, delta))
                except Exception:
                    pass
        ok = True
    else:
        ollama_scrape_errors.labels(endpoint="/api/ps").inc()

    return ok


def _collect_loop():
    while True:
        try:
            success = _scrape()
            ollama_up.set(1 if success else 0)
            if success:
                ollama_last_scrape.set(time.time())
        except Exception as exc:
            log.error("Unexpected scrape error: %s", exc)
            ollama_up.set(0)
        time.sleep(SCRAPE_INTERVAL)


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/metrics", "/metrics/"):
            output = generate_latest(registry)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        elif self.path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok\n")
        else:
            self.send_response(404)
            self.end_headers()


def main():
    log.info("Ollama exporter starting on port %d → %s", EXPORTER_PORT, OLLAMA_URL)

    t = threading.Thread(target=_collect_loop, daemon=True, name="ollama-collect")
    t.start()

    server = HTTPServer(("0.0.0.0", EXPORTER_PORT), MetricsHandler)
    log.info("Serving /metrics on http://0.0.0.0:%d", EXPORTER_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
