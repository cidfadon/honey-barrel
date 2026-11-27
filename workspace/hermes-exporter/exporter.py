#!/usr/bin/env python3

import time
import requests

from prometheus_client import (
    start_http_server,
    Gauge,
    Counter,
    Histogram
)


HERMES_URL = "http://hermes:8642"
EXPORTER_PORT = 9105


hermes_up = Gauge(
    "hermes_up",
    "Hermes API availability"
)

hermes_api_latency = Histogram(
    "hermes_api_latency_seconds",
    "Hermes API response latency"
)

hermes_api_errors = Counter(
    "hermes_api_errors_total",
    "Hermes API errors"
)

hermes_last_check = Gauge(
    "hermes_last_check_timestamp",
    "Last Hermes check timestamp"
)


def check_hermes():

    start = time.time()

    try:
        response = requests.get(
            HERMES_URL,
            timeout=5
        )

        latency = time.time() - start

        hermes_api_latency.observe(latency)

        if response.status_code < 400:
            hermes_up.set(1)
        else:
            hermes_up.set(0)
            hermes_api_errors.inc()

    except Exception:
        hermes_up.set(0)
        hermes_api_errors.inc()

    hermes_last_check.set(time.time())


def main():

    print(
        f"Starting Hermes exporter on port {EXPORTER_PORT}"
    )

    start_http_server(EXPORTER_PORT)

    while True:
        check_hermes()
        time.sleep(15)


if __name__ == "__main__":
    main()

