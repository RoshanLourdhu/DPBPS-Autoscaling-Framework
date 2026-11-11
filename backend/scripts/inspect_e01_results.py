import json
from pathlib import Path

exp_dir = Path("results/experiments/exp_20261110T152425_normal_traffic_838109a5")
with open(exp_dir / "telemetry_metrics.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total snapshots: {data['total_snapshots']}")
for i, snap in enumerate(data["snapshots"]):
    fe = snap["services"].get("frontend", {})
    cart = snap["services"].get("cartservice", {})
    prod = snap["services"].get("productcatalogservice", {})
    check = snap["services"].get("checkoutservice", {})
    cur = snap["services"].get("currencyservice", {})
    rec = snap["services"].get("recommendationservice", {})
    ad = snap["services"].get("adservice", {})
    pay = snap["services"].get("paymentservice", {})
    ship = snap["services"].get("shippingservice", {})
    email = snap["services"].get("emailservice", {})
    
    elapsed = snap["elapsed_seconds"]
    active_services = [k for k, v in snap["services"].items() if v.get("telemetry_available")]
    print(f"Snap {i:2d} (t={elapsed:5.1f}s): Active={len(active_services):2d}/10 | FE: RPS={fe.get('request_rate', '--')} P95={fe.get('p95_latency_ms', '--')} CPU%={fe.get('cpu_utilization_percent', '--')} | Cart: RPS={cart.get('request_rate', '--')} | Checkout: RPS={check.get('request_rate', '--')}")

