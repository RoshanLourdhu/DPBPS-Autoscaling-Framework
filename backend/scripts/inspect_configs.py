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

for code, eid in exp_ids.items():
    p = os.path.join(base_dir, eid)
    cfg_path = os.path.join(p, "experiment_config.json")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(p, "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    print(f"=== {code}: {cfg.get('profile_name')} ===")
    print(f"  Target users: {cfg.get('target_users')}, Duration: {cfg.get('target_duration_seconds')}, Spawn rate: {cfg.get('spawn_rate')}")
    print(f"  Stages: {cfg.get('stages')}")

# Also check backend/workload/profiles.py
print("\n=== backend/workload/profiles.py INSPECTION ===")
with open(r"D:\CIS\Deployment Aware AAutoscaling Platform\backend\workload\profiles.py") as f:
    code_text = f.read()

import re
profiles = re.findall(r"(\w+)\s*=\s*WorkloadProfile\(.*?\)", code_text, re.DOTALL)
print(f"Found {len(profiles)} profiles defined in backend/workload/profiles.py")

