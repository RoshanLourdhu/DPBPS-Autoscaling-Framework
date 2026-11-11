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

for code, eid in exp_ids.items():
    p = os.path.join(base_dir, eid, "telemetry_metrics.json")
    with open(p) as f:
        tm = json.load(f)
    snaps = tm.get("snapshots", [])
    
    for i, s in enumerate(snaps):
        services = s.get("services", {})
        for svc in services_10:
            if svc in services:
                sd = services[svc]
                avail = sd.get("telemetry_available", True)
                cpu = sd.get("cpu_usage_millicores")
                mem = sd.get("memory_usage_mib")
                if not (avail and cpu is not None and mem is not None):
                    print(f"{code} snap {i} (t={s.get('elapsed_seconds')}s): {svc} - avail={avail}, cpu={cpu}, mem={mem}")

