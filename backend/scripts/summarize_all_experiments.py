import json
import os

experiments = {
    'E01': 'exp_20261110T152425_normal_traffic_838109a5',
    'E02': 'exp_20261110T165351_gradual_traffic_increase_309b2d79',
    'E03': 'exp_20261110T170244_sudden_traffic_spike_d80c4694',
    'E04': 'exp_20261110T172135_sustained_high_traffic_51ce3165',
    'E05': 'exp_20261110T172806_traffic_decrease_71144bfe',
    'E06': 'exp_20261110T173312_bursty_traffic_55733a14'
}

base = r'D:\CIS\Deployment Aware AAutoscaling Platform\results\experiments'

for exp_code, exp_id in experiments.items():
    p = os.path.join(base, exp_id)
    with open(os.path.join(p, 'experiment_summary.json')) as f:
        summ = json.load(f)
    with open(os.path.join(p, 'telemetry_metrics.json')) as f:
        tm = json.load(f)
    with open(os.path.join(p, 'dpbps_decisions.json')) as f:
        dm = json.load(f)
    with open(os.path.join(p, 'actuator_audit.json')) as f:
        am = json.load(f)
    
    snaps = tm.get('snapshots', [])
    fe_rps = [s['services']['frontend']['request_rate'] for s in snaps if s.get('services', {}).get('frontend', {}).get('request_rate') is not None]
    fe_p95 = [s['services']['frontend']['p95_latency_ms'] for s in snaps if s.get('services', {}).get('frontend', {}).get('p95_latency_ms') is not None]
    fe_cpu = [s['services']['frontend']['cpu_usage_millicores'] for s in snaps if s.get('services', {}).get('frontend', {}).get('cpu_usage_millicores') is not None]
    fe_mem = [s['services']['frontend']['memory_usage_mib'] for s in snaps if s.get('services', {}).get('frontend', {}).get('memory_usage_mib') is not None]
    prod_rps = [s['services']['productcatalogservice']['request_rate'] for s in snaps if s.get('services', {}).get('productcatalogservice', {}).get('request_rate') is not None]
    cart_rps = [s['services']['cartservice']['request_rate'] for s in snaps if s.get('services', {}).get('cartservice', {}).get('request_rate') is not None]

    print(f"=== {exp_code}: {summ.get('profile_name')} ({exp_id}) ===")
    print(f"Duration: {summ.get('duration_seconds')}s (Target: {summ.get('target_duration_seconds')}s)")
    print(f"Frontend RPS: Avg={summ.get('average_frontend_rps'):.2f}, Peak={summ.get('peak_frontend_rps'):.2f}")
    print(f"Frontend P95: Avg={summ.get('average_frontend_p95_ms'):.2f}ms, Max={summ.get('max_frontend_p95_ms'):.2f}ms")
    print(f"ProductCatalog RPS Peak: {max(prod_rps) if prod_rps else 0:.2f} | CartService RPS Peak: {max(cart_rps) if cart_rps else 0:.2f}")
    print(f"Frontend CPU: Avg={sum(fe_cpu)/len(fe_cpu) if fe_cpu else 0:.1f}m, Peak={max(fe_cpu) if fe_cpu else 0:.1f}m | Mem Peak={max(fe_mem) if fe_mem else 0:.1f}MiB")
    print(f"Decisions: HOLD={dm.get('hold_count')}, SCALE_UP={dm.get('scale_up_count')}, SCALE_DOWN={dm.get('scale_down_count')}, Bottlenecks={dm.get('bottlenecks_detected')}")
    print(f"Actuator mode: {am.get('execution_mode')}, cluster_modified: {summ.get('cluster_modified')}")
    print()
