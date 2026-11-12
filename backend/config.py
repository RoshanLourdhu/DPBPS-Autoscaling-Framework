# backend/config.py
"""Central configuration module.
Provides access to environment‑based flags used across the backend.
"""
import os

# Scaling flag – defaults to False (dry‑run / simulation mode)
SCALING_ENABLED = os.getenv("SCALING_ENABLED", "false").lower() == "true"

# Optional allowlist of services that may be scaled (comma‑separated list)
# If empty, all approved services are allowed.
SCALING_ALLOWLIST = [s.strip() for s in os.getenv("SCALING_ALLOWLIST", "").split(",") if s.strip()]

# Prometheus configuration
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
PROMETHEUS_TIMEOUT_SECONDS = float(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "10.0"))
PROMETHEUS_MAX_AGE_SECONDS = float(os.getenv("PROMETHEUS_MAX_AGE_SECONDS", "60.0"))

# Kubernetes namespaces
KUBERNETES_NAMESPACE = os.getenv("KUBERNETES_NAMESPACE", "online-boutique")
KUBERNETES_MONITORING_NAMESPACE = os.getenv("KUBERNETES_MONITORING_NAMESPACE", "monitoring")
PROMETHEUS_SERVICE_NAME = os.getenv("PROMETHEUS_SERVICE_NAME", "dpbps-monitoring-kube-prom-prometheus")
PROMETHEUS_SERVICE_PORT = int(os.getenv("PROMETHEUS_SERVICE_PORT", "9090"))

# CI/CD & Deployment State Configuration
CICD_WEBHOOK_SECRET = os.getenv("CICD_WEBHOOK_SECRET", "dpbps-cicd-secret-token")
DEPLOYMENT_STATE_FILE = os.getenv(
    "DEPLOYMENT_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "deployment_state.json"),
)


