import json
import sys
from typing import Dict, Tuple
import httpx

# Service URLs (adjusted to match Docker Compose ports)
SERVICE_URLS = {
    "orchestration-api": "http://localhost:8000/api/v1/health",
    "product-service": "http://localhost:8001/api/v1/health",
    "cart-service": "http://localhost:8002/api/v1/health",
    "checkout-service": "http://localhost:8003/api/v1/health",
    "recommendation-service": "http://localhost:8004/api/v1/health",
    "frontend": "http://localhost:8080",
    "postgres": None,
}

class ReadinessError(RuntimeError):
    """Raised when any required service is unhealthy."""

def _probe(url: str, timeout: float = 5.0) -> Tuple[bool, str]:
    try:
        r = httpx.get(url, timeout=timeout)
        if r.status_code == 200:
            return True, "ok"
        return False, f"status {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)

def _check_postgres() -> Tuple[bool, str]:
    try:
        import pg8000
        conn = pg8000.connect(
            user="dpbps_user",
            password="dpbps_pass",
            host="localhost",
            port=5432,
            database="dpbps",
        )
        conn.close()
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        return False, str(e)

def run() -> Dict[str, Dict]:
    """Perform checks, output JSON to stdout, exit non‑zero on failure."""
    results: Dict[str, Dict] = {}
    for name, url in SERVICE_URLS.items():
        if url is None:
            continue
        healthy, reason = _probe(url)
        results[name] = {"healthy": healthy, "reason": reason}
    healthy, reason = _check_postgres()
    results["postgres"] = {"healthy": healthy, "reason": reason}

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.flush()
    if not all(v["healthy"] for v in results.values()):
        raise ReadinessError("One or more services are unhealthy.")
    return results

if __name__ == "__main__":
    try:
        run()
    except ReadinessError:
        sys.exit(1)
