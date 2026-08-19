#!/usr/bin/env python3
"""Hermes Prometheus metrics sidecar.

Runs inside the Hermes container on port 9106. Exposes /metrics by polling
the Hermes dashboard API (port 9119) using the embedded session token.
"""

import re
import time
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from prometheus_client import (
    Gauge,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s hermes-metrics %(levelname)s %(message)s",
)
log = logging.getLogger("hermes-metrics")

HERMES_DASHBOARD_URL = "http://localhost:9119"
METRICS_PORT = 9106
SCRAPE_INTERVAL = 15  # seconds
TOKEN_REFRESH_INTERVAL = 300  # 5 minutes

registry = CollectorRegistry()

# --- Availability ---
hermes_up = Gauge("hermes_up", "Hermes API availability (1=up, 0=down)", registry=registry)
hermes_api_latency = Histogram(
    "hermes_api_latency_seconds",
    "Hermes API response latency in seconds",
    ["endpoint"],
    registry=registry,
)

# --- Session stats (from /api/sessions/stats) ---
hermes_sessions_total = Gauge(
    "hermes_sessions_total",
    "Total number of Hermes sessions",
    registry=registry,
)
hermes_sessions_active = Gauge(
    "hermes_sessions_active_store",
    "Sessions in active store",
    registry=registry,
)
hermes_sessions_archived = Gauge(
    "hermes_sessions_archived",
    "Archived sessions count",
    registry=registry,
)
hermes_messages_total = Gauge(
    "hermes_messages_total",
    "Total number of messages across all sessions",
    registry=registry,
)
hermes_sessions_by_source = Gauge(
    "hermes_sessions_by_source",
    "Sessions count broken down by source (cli, tui, api, ...)",
    ["source"],
    registry=registry,
)

# --- Status metrics (from /api/status) ---
hermes_active_sessions = Gauge(
    "hermes_active_sessions",
    "Number of currently active Hermes sessions",
    registry=registry,
)
hermes_gateway_running = Gauge(
    "hermes_gateway_running",
    "1 if the Hermes gateway is running",
    registry=registry,
)

# --- Recent session token & tool usage (from /api/sessions, last 50) ---
hermes_recent_input_tokens = Gauge(
    "hermes_recent_input_tokens_total",
    "Sum of input tokens across the most recent sessions",
    registry=registry,
)
hermes_recent_output_tokens = Gauge(
    "hermes_recent_output_tokens_total",
    "Sum of output tokens across the most recent sessions",
    registry=registry,
)
hermes_recent_tool_calls = Gauge(
    "hermes_recent_tool_calls_total",
    "Sum of tool calls across the most recent sessions",
    registry=registry,
)
hermes_recent_cache_read_tokens = Gauge(
    "hermes_recent_cache_read_tokens_total",
    "Sum of cache-read tokens across the most recent sessions",
    registry=registry,
)

# --- Scrape health ---
hermes_scrape_errors = Counter(
    "hermes_scrape_errors_total",
    "Number of failed Hermes API scrapes",
    ["endpoint"],
    registry=registry,
)
hermes_last_scrape = Gauge(
    "hermes_last_scrape_timestamp_seconds",
    "Unix timestamp of the last successful Hermes API scrape",
    registry=registry,
)

# Shared mutable state (protected by a lock)
_lock = threading.Lock()
_token: str = ""


def _fetch_token() -> str:
    """Extract embedded session token from the Hermes dashboard HTML."""
    try:
        r = requests.get(f"{HERMES_DASHBOARD_URL}/", timeout=5)
        match = re.search(r'HERMES_SESSION_TOKEN__="([^"]+)"', r.text)
        if match:
            return match.group(1)
    except Exception as exc:
        log.warning("Could not fetch Hermes session token: %s", exc)
    return ""


def _get(path: str, token: str, timeout: int = 10) -> tuple[dict | None, float]:
    """GET a Hermes API path; returns (data, latency_seconds)."""
    url = f"{HERMES_DASHBOARD_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    start = time.monotonic()
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        latency = time.monotonic() - start
        if r.status_code == 200:
            return r.json(), latency
        log.debug("GET %s → HTTP %d", path, r.status_code)
        return None, latency
    except Exception as exc:
        latency = time.monotonic() - start
        log.warning("GET %s failed: %s", path, exc)
        return None, latency


def _scrape(token: str) -> bool:
    """Collect all metrics from Hermes API. Returns True on success."""
    ok = False

    # /api/sessions/stats
    data, lat = _get("/api/sessions/stats", token)
    hermes_api_latency.labels(endpoint="/api/sessions/stats").observe(lat)
    if data:
        hermes_sessions_total.set(data.get("total", 0))
        hermes_sessions_active.set(data.get("active_store", 0))
        hermes_sessions_archived.set(data.get("archived", 0))
        hermes_messages_total.set(data.get("messages", 0))
        for source, count in (data.get("by_source") or {}).items():
            hermes_sessions_by_source.labels(source=source).set(count)
        ok = True
    else:
        hermes_scrape_errors.labels(endpoint="/api/sessions/stats").inc()

    # /api/status
    data, lat = _get("/api/status", token)
    hermes_api_latency.labels(endpoint="/api/status").observe(lat)
    if data:
        hermes_active_sessions.set(data.get("active_sessions", 0))
        hermes_gateway_running.set(1 if data.get("gateway_running") else 0)
        ok = True
    else:
        hermes_scrape_errors.labels(endpoint="/api/status").inc()

    # /api/sessions — aggregate token / tool usage from the last 50 sessions
    data, lat = _get("/api/sessions?limit=50", token)
    hermes_api_latency.labels(endpoint="/api/sessions").observe(lat)
    if data and isinstance(data.get("sessions"), list):
        sessions = data["sessions"]
        hermes_recent_input_tokens.set(sum(s.get("input_tokens") or 0 for s in sessions))
        hermes_recent_output_tokens.set(sum(s.get("output_tokens") or 0 for s in sessions))
        hermes_recent_tool_calls.set(sum(s.get("tool_call_count") or 0 for s in sessions))
        hermes_recent_cache_read_tokens.set(sum(s.get("cache_read_tokens") or 0 for s in sessions))
        ok = True
    else:
        hermes_scrape_errors.labels(endpoint="/api/sessions").inc()

    return ok


def _collect_loop():
    """Background thread: refresh token and scrape metrics periodically."""
    global _token
    last_token_refresh = 0.0

    while True:
        now = time.monotonic()

        # Refresh token periodically
        if now - last_token_refresh > TOKEN_REFRESH_INTERVAL:
            new_token = _fetch_token()
            if new_token:
                with _lock:
                    _token = new_token
                last_token_refresh = now
                log.info("Hermes session token refreshed.")
            else:
                log.warning("Token refresh failed; will retry next cycle.")

        with _lock:
            token = _token

        if not token:
            hermes_up.set(0)
            hermes_scrape_errors.labels(endpoint="token").inc()
            time.sleep(SCRAPE_INTERVAL)
            continue

        try:
            success = _scrape(token)
            hermes_up.set(1 if success else 0)
            if success:
                hermes_last_scrape.set(time.time())
        except Exception as exc:
            log.error("Unexpected scrape error: %s", exc)
            hermes_up.set(0)

        time.sleep(SCRAPE_INTERVAL)


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress access log noise
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
    log.info("Hermes metrics sidecar starting on port %d", METRICS_PORT)

    # Initial token fetch (block until obtained or first timeout)
    global _token
    for attempt in range(10):
        tok = _fetch_token()
        if tok:
            _token = tok
            log.info("Initial session token obtained.")
            break
        log.info("Waiting for Hermes dashboard (attempt %d/10)…", attempt + 1)
        time.sleep(5)

    # Launch background collection thread
    t = threading.Thread(target=_collect_loop, daemon=True, name="hermes-metrics-collect")
    t.start()

    server = HTTPServer(("0.0.0.0", METRICS_PORT), MetricsHandler)
    log.info("Serving /metrics on http://0.0.0.0:%d", METRICS_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
