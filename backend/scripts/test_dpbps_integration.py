import json
from fastapi.testclient import TestClient
from backend.app.main import app

def main():
    client = TestClient(app)
    
    print("=== DPBPS PIPELINE AND API INTEGRATION VERIFICATION ===")
    
    # 1. Health
    r_health = client.get("/api/v1/health")
    print("1. /health:", r_health.status_code, r_health.json())
    
    # 2. Services
    r_services = client.get("/api/v1/services")
    print(f"2. /services: {r_services.status_code}, count={len(r_services.json())}")
    
    # 3. Deployments
    r_deployments = client.get("/api/v1/deployments")
    print(f"3. /deployments: {r_deployments.status_code}, count={len(r_deployments.json())}")
    
    # 4. Kubernetes telemetry
    r_telemetry = client.get("/api/v1/kubernetes/telemetry")
    print(f"4. /kubernetes/telemetry: {r_telemetry.status_code}, count={len(r_telemetry.json())}")
    
    # 5. Kubernetes telemetry summary
    r_summary = client.get("/api/v1/kubernetes/telemetry/summary")
    s_data = r_summary.json()
    print(f"5. /kubernetes/telemetry/summary: {r_summary.status_code}, total={s_data.get('deployment_count')}, complete={s_data.get('complete_telemetry_count')}")
    
    # 6. DPBPS pipeline evaluate
    r_eval = client.get("/api/v1/dpbps/pipeline/evaluate")
    print(f"6. /dpbps/pipeline/evaluate: {r_eval.status_code}")
    eval_data = r_eval.json()
    print("   Total Services:", eval_data.get("total_services"))
    print("   Execution Mode:", eval_data.get("execution_mode"))
    print("   Cluster Modified:", eval_data.get("cluster_modified"))
    print("   Deployment Phase:", eval_data.get("deployment_phase"))
    print("   Complete Telemetry Services:", eval_data.get("complete_telemetry_services"))
    print("   Incomplete Telemetry Services:", eval_data.get("incomplete_telemetry_services"))
    print("   Hold Count:", eval_data.get("hold_count"))
    print("   Scale Up Count:", eval_data.get("scale_up_count"))
    print("   Scale Down Count:", eval_data.get("scale_down_count"))
    print("   Bottleneck Service:", eval_data.get("bottleneck_service"))
    
    print("\nService Details:")
    header = f"{'SERVICE':24} | {'DECISION':8} | {'REPLICAS':8} | {'ACTUATOR':10} | {'COMPLETE':8} | {'REASON'}"
    print(header)
    print("-" * 110)
    for s in eval_data.get("services", []):
        name = s.get("service_name")
        dec = s.get("dpbps_decision")
        cur_rep = s.get("current_replicas")
        prop_rep = s.get("proposed_replica_count")
        act = s.get("actuator_execution_status")
        comp = s.get("telemetry_complete")
        reason = s.get("reason")
        print(f"{name:24} | {dec:8} | {cur_rep}->{prop_rep:4} | {act:10} | {str(comp):8} | {reason}")
    
    # 7. Experiments profiles
    r_profiles = client.get("/api/v1/experiments/profiles")
    print(f"\n7. /experiments/profiles: {r_profiles.status_code}, count={len(r_profiles.json())}")
    
    # 8. Experiments registry
    r_experiments = client.get("/api/v1/experiments")
    print(f"8. /experiments: {r_experiments.status_code}, count={len(r_experiments.json())}")

if __name__ == "__main__":
    main()
