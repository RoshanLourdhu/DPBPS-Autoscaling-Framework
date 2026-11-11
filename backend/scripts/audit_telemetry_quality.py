import json
import os

base_dir = r"D:\CIS\Deployment Aware AAutoscaling Platform\results\experiments"
exp_ids = {
    "E01": "exp_20261110T152425_normal_traffic_838109a5",
    "E02": "exp_20261110T165351_gradual_traffic_increase_309b2d79",
    "E03": "exp_20261110T170244_sudden_traffic_spike_d80c4694",
    "E04": "exp_20261110T172135_sustained_high_traffic_51ce3165",
    "E05": "exp_20261110T172806_traffic_decrease_71144bfe",
    "E06": "exp_20261110T173312_bursty_traffic_55733a14"
}

services_10 = [
    "frontend", "cartservice", "productcatalogservice", "currencyservice",
    "paymentservice", "shippingservice", "emailservice", "checkoutservice",
    "recommendationservice", "adservice"
]

print("=== DETAILED TELEMETRY QUALITY AUDIT ===")
total_obs = 0
total_valid_obs = 0
missing_metrics_count = 0

for code, eid in exp_ids.items():
    p = os.path.join(base_dir, eid, "telemetry_metrics.json")
    with open(p) as f:
        tm = json.load(f)
    snaps = tm.get("snapshots", [])
    print(f"\n{code} ({eid}): {len(snaps)} snapshots")
    
    for i, s in enumerate(snaps):
        services = s.get("services", {})
        for svc in services_10:
            total_obs += 1
            if svc not in services:
                print(f"  [MISSING SERVICE] {svc} missing in snap {i}")
                missing_metrics_count += 1
                continue
            sd = services[svc]
            # Check availability
            avail = sd.get("telemetry_available", True)
            rps = sd.get("request_rate")
            cpu = sd.get("cpu_usage_millicores")
            mem = sd.get("memory_usage_mib")
            p95 = sd.get("p95_latency_ms")
            
            # Count valid observations
            if avail and cpu is not None and mem is not None:
                total_valid_obs += 1
            else:
                missing_metrics_count += 1

print(f"\nTotal observations checked: {total_obs}")
print(f"Total fully valid observations: {total_valid_obs}")
print(f"Missing / incomplete observations: {missing_metrics_count}")

