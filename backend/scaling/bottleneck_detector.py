# backend/scaling/bottleneck_detector.py
"""Simple bottleneck detection based on dependency graph and telemetry.

The detector examines latency and error rate of each service and its downstream
dependencies. If a downstream service exhibits high latency or error rate, the
upstream service is considered to be *affected* by a bottleneck.

The function returns the name of the most severe bottleneck service (or ``None``
if no bottleneck is detected). A deterministic tie‑break is achieved by sorting
service names.
"""

from typing import Dict, List, Optional
from .models import TelemetryInput

# Define the static dependency graph for the project. Adjust if the actual
# relationships differ.
# Example: checkout depends on cart, which depends on product.
DEPENDENCY_GRAPH: Dict[str, List[str]] = {
    "product": [],
    "cart": ["product"],
    "checkout": ["cart"],
    "recommendation": ["product"],
}

# Thresholds that signal a problematic downstream service.
LATENCY_THRESHOLD_MS = 500  # ms
ERROR_RATE_THRESHOLD = 0.05  # 5 %


def detect_bottleneck(telemetry: List[TelemetryInput]) -> Optional[str]:
    """Return the name of a service that is a bottleneck.

    The algorithm identifies services whose latency or error rate exceed
    defined thresholds and selects the most severe one (by latency, then error).
    """
    telemetry_by_name: Dict[str, TelemetryInput] = {t.service_name: t for t in telemetry}
    # Gather services exceeding thresholds
    exceeding: List[TelemetryInput] = [
        t for t in telemetry_by_name.values()
        if t.p95_latency > LATENCY_THRESHOLD_MS or t.error_rate > ERROR_RATE_THRESHOLD
    ]
    if not exceeding:
        return None
    # Choose most severe service – prioritize higher latency, then higher error rate
    exceeding.sort(key=lambda x: (x.p95_latency, x.error_rate), reverse=True)
    return exceeding[0].service_name
