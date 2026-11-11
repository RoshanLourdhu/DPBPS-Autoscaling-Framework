import os
import json

base_dir = r"D:\CIS\Deployment Aware AAutoscaling Platform\results\experiments"

print("--- INVESTIGATING E01 LATENCY SERIES ---")
e01_path = os.path.join(base_dir, "exp_20261110T152425_normal_traffic_838109a5", "telemetry_metrics.json")
with open(e01_path) as f:
    e01_tm = json.load(f)

e01_snaps = e01_tm.get("snapshots", [])
print(f"E01 total snapshots: {len(e01_snaps)}")
e01_p95_list = []
for i, s in enumerate(e01_snaps):
    t = s.get("elapsed_seconds")
    st = s.get("stage")
    fe = s.get("services", {}).get("frontend", {})
    p95 = fe.get("p95_latency_ms")
    p50 = fe.get("p50_latency_ms")
    rps = fe.get("request_rate")
    p95_str = f"{p95:7.2f} ms" if p95 is not None else "   None"
    p50_str = f"{p50:5.2f} ms" if p50 is not None else " None"
    rps_str = f"{rps:5.2f}" if rps is not None else " None"
    t_str = f"{t:5.1f}s" if t is not None else " None"
    e01_p95_list.append(p95)
    print(f"Snap {i:2d} (t={t_str}, stage={st}): P95={p95_str}, P50={p50_str}, RPS={rps_str}")

all_avg = sum(e01_p95_list) / len(e01_p95_list)
print(f"All snapshots average P95: {all_avg:.2f} ms")
# Steady state excluding snap 0 and snap 1 (warmup t <= 10s)
steady_p95_list = e01_p95_list[2:]
steady_avg = sum(steady_p95_list) / len(steady_p95_list) if steady_p95_list else 0
print(f"Excluding warmup (t >= 20s, snaps 2..{len(e01_snaps)-1}) average P95: {steady_avg:.2f} ms")


print("\n--- INVESTIGATING E02 LATENCY SERIES ---")
e02_path = os.path.join(base_dir, "exp_20261110T165351_gradual_traffic_increase_309b2d79", "telemetry_metrics.json")
with open(e02_path) as f:
    e02_tm = json.load(f)

e02_snaps = e02_tm.get("snapshots", [])
print(f"E02 total snapshots: {len(e02_snaps)}")
e02_p95_list = []
for i, s in enumerate(e02_snaps):
    t = s.get("elapsed_seconds")
    st = s.get("stage")
    fe = s.get("services", {}).get("frontend", {})
    p95 = fe.get("p95_latency_ms")
    p50 = fe.get("p50_latency_ms")
    rps = fe.get("request_rate")
    p95_str = f"{p95:7.2f} ms" if p95 is not None else "   None"
    p50_str = f"{p50:5.2f} ms" if p50 is not None else " None"
    rps_str = f"{rps:5.2f}" if rps is not None else " None"
    t_str = f"{t:5.1f}s" if t is not None else " None"
    e02_p95_list.append(p95)
    print(f"Snap {i:2d} (t={t_str}, stage={st}): P95={p95_str}, P50={p50_str}, RPS={rps_str}")

e02_all_avg = sum(e02_p95_list) / len(e02_p95_list)
print(f"E02 all snapshots average P95: {e02_all_avg:.2f} ms")
print(f"E02 all snapshots max P95: {max(e02_p95_list):.2f} ms")

# Let's check stage by stage
stage1 = [e02_p95_list[i] for i, s in enumerate(e02_snaps) if s.get("elapsed_seconds", 0) <= 60]
stage2 = [e02_p95_list[i] for i, s in enumerate(e02_snaps) if 60 < s.get("elapsed_seconds", 0) <= 120]
stage3 = [e02_p95_list[i] for i, s in enumerate(e02_snaps) if s.get("elapsed_seconds", 0) > 120]

print(f"Stage 1 (10u, 0-60s) avg={sum(stage1)/len(stage1):.2f} ms, max={max(stage1):.2f} ms")
print(f"Stage 2 (25u, 60-120s) avg={sum(stage2)/len(stage2):.2f} ms, max={max(stage2):.2f} ms")
print(f"Stage 3 (50u, 120-180s) avg={sum(stage3)/len(stage3):.2f} ms, max={max(stage3):.2f} ms")

# Check workload_metrics.json for E02 to see where 185.80 ms came from!
e02_wl_path = os.path.join(base_dir, "exp_20261110T165351_gradual_traffic_increase_309b2d79", "workload_metrics.json")
if os.path.exists(e02_wl_path):
    with open(e02_wl_path) as f:
        e02_wl = json.load(f)
    print("\nE02 workload_metrics.json content:")
    print(json.dumps(e02_wl, indent=2))
