import os
import json
from datetime import datetime

base_dir = r"D:\CIS\Deployment Aware AAutoscaling Platform\results\experiments"

exp_ids = {
    "E01": "exp_20261110T152425_normal_traffic_838109a5",
    "E02": "exp_20261110T165351_gradual_traffic_increase_309b2d79",
    "E03": "exp_20261110T170244_sudden_traffic_spike_d80c4694",
    "E04": "exp_20261110T172135_sustained_high_traffic_51ce3165",
    "E05": "exp_20261110T172806_traffic_decrease_71144bfe",
    "E06": "exp_20261110T173312_bursty_traffic_55733a14"
}

print("=" * 80)
print("AUDIT: INSPECTING ALL 6 EXPERIMENT DATASETS")
print("=" * 80)

audit_results = {}

for code, eid in exp_ids.items():
    p = os.path.join(base_dir, eid)
    exists = os.path.exists(p)
    print(f"\n--- {code}: {eid} (Exists: {exists}) ---")
    if not exists:
        continue
    
    files = os.listdir(p)
    print(f"Files ({len(files)}): {sorted(files)}")
    
    # Load summary
    summary_path = os.path.join(p, "experiment_summary.json")
    summary = {}
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            summary = json.load(f)
            
    # Load config
    cfg_path = os.path.join(p, "experiment_config.json")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(p, "config.json")
    config = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            config = json.load(f)

    # Load telemetry
    telem_path = os.path.join(p, "telemetry_metrics.json")
    telemetry = {}
    if os.path.exists(telem_path):
        with open(telem_path) as f:
            telemetry = json.load(f)
            
    # Load decisions
    dec_path = os.path.join(p, "dpbps_decisions.json")
    decisions = {}
    if os.path.exists(dec_path):
        with open(dec_path) as f:
            decisions = json.load(f)

    # Load workload
    wl_path = os.path.join(p, "workload_metrics.json")
    workload = {}
    if os.path.exists(wl_path):
        with open(wl_path) as f:
            workload = json.load(f)

    # Load actuator
    act_path = os.path.join(p, "actuator_audit.json")
    actuator = {}
    if os.path.exists(act_path):
        with open(act_path) as f:
            actuator = json.load(f)

    snapshots = telemetry.get("snapshots", []) if isinstance(telemetry, dict) else (telemetry if isinstance(telemetry, list) else [])
    
    # Analyze frontend latencies across snapshots
    fe_p95_snaps = []
    fe_rps_snaps = []
    fe_cpu_snaps = []
    for s in snapshots:
        fe = s.get("services", {}).get("frontend", {})
        p95 = fe.get("p95_latency_ms")
        rps = fe.get("request_rate")
        cpu = fe.get("cpu_usage_millicores")
        elapsed = s.get("elapsed_seconds")
        stage = s.get("stage")
        fe_p95_snaps.append((elapsed, stage, p95))
        if rps is not None:
            fe_rps_snaps.append(rps)
        if cpu is not None:
            fe_cpu_snaps.append(cpu)

    # Analyze decision items in detail
    evaluations = decisions.get("evaluations", []) if isinstance(decisions, dict) else (decisions if isinstance(decisions, list) else [])
    hold_count = 0
    up_count = 0
    down_count = 0
    up_details = []
    
    for ev in evaluations:
        decs = ev.get("decisions", []) if isinstance(ev, dict) else []
        for d in decs:
            act = d.get("action") or d.get("decision_type")
            if act == "HOLD":
                hold_count += 1
            elif act == "SCALE_UP":
                up_count += 1
                up_details.append((ev.get("timestamp"), d.get("service_name"), d.get("current_replicas"), d.get("target_replicas"), d.get("reason")))
            elif act == "SCALE_DOWN":
                down_count += 1

    total_recalculated_decisions = hold_count + up_count + down_count

    audit_results[code] = {
        "summary": summary,
        "config": config,
        "snapshot_count": len(snapshots),
        "fe_p95_snaps": fe_p95_snaps,
        "fe_rps_avg": sum(fe_rps_snaps)/len(fe_rps_snaps) if fe_rps_snaps else 0,
        "fe_rps_max": max(fe_rps_snaps) if fe_rps_snaps else 0,
        "fe_cpu_avg": sum(fe_cpu_snaps)/len(fe_cpu_snaps) if fe_cpu_snaps else 0,
        "fe_cpu_max": max(fe_cpu_snaps) if fe_cpu_snaps else 0,
        "decision_summary_reported": {
            "hold": decisions.get("hold_count") if isinstance(decisions, dict) else summary.get("scaling_decisions_hold"),
            "up": decisions.get("scale_up_count") if isinstance(decisions, dict) else summary.get("scaling_decisions_scale_up"),
            "down": decisions.get("scale_down_count") if isinstance(decisions, dict) else summary.get("scaling_decisions_scale_down")
        },
        "decision_recalculated": {
            "hold": hold_count,
            "up": up_count,
            "down": down_count,
            "total": total_recalculated_decisions
        },
        "up_details": up_details,
        "workload_locust_stats": workload.get("locust_stats", {})
    }

    print(f"Summary duration: {summary.get('duration_seconds')}s, target: {summary.get('target_duration_seconds')}s")
    print(f"Frontend RPS: summary avg={summary.get('average_frontend_rps')}, peak={summary.get('peak_frontend_rps')}")
    print(f"Frontend P95: summary avg={summary.get('average_frontend_p95_ms')}, peak={summary.get('max_frontend_p95_ms')}")
    print(f"Decisions reported in summary/dec: HOLD={audit_results[code]['decision_summary_reported']['hold']}, UP={audit_results[code]['decision_summary_reported']['up']}, DOWN={audit_results[code]['decision_summary_reported']['down']}")
    print(f"Decisions recalculated directly: HOLD={hold_count}, UP={up_count}, DOWN={down_count}, TOTAL={total_recalculated_decisions}")
    if up_details:
        print(f"SCALE_UP events ({len(up_details)}):")
        for u in up_details:
            print(f"   {u}")

print("\n" + "=" * 80)
print("AUDIT SCRIPT EXECUTION FINISHED")
print("=" * 80)

