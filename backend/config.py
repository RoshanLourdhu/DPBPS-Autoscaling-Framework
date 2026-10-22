# backend/config.py
"""Central configuration module.
Provides access to environment‑based flags used across the backend.
"""
import os

# Scaling flag – defaults to False (dry‑run / simulation mode)
SCALING_ENABLED = os.getenv("SCALING_ENABLED", "false").lower() == "true"

# Optional allowlist of services that may be scaled (comma‑separated list)
# If empty, all services are allowed.
SCALING_ALLOWLIST = [s.strip() for s in os.getenv("SCALING_ALLOWLIST", "").split(",") if s.strip()]
