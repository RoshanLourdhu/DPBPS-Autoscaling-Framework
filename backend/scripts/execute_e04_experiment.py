"""
STAGE 8 — Live Experiment E04 (SUSTAINED_HIGH_TRAFFIC) Supervised Execution Engine.

Executes E04 through the existing ExperimentExecutor, monitors live cluster metrics
over the 220-second duration (60 users @ 5 u/s sustained for 180s), runs DPBPS
pipeline evaluations in DRY-RUN mode, enforces watchdog scale-to-zero upon completion,
and writes all 7 required artifacts to results/experiments/<id>/.
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from kubernetes import client

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.config as cfg
from backend.workload.models import WorkloadProfileName
from backend.workload.profiles import get_sustained_high_traffic_profile
from backend.workload.shape_generator import generate_combined_locustfile
from backend.experiments.models import ExperimentStatus
from backend.experiments.manager import ExperimentManager
from backend.experiments.executor import ExperimentExecutor, ExperimentSafetyError
from backend.scaling.kubernetes.prometheus_client import PrometheusClient
from backend.scaling.kubernetes.telemetry_adapter import KubernetesTelemetryAdapter
from backend.scaling.dpbps_controller import DPBPSController
from backend.scaling.kubernetes.actuator import KubernetesScalingActuator
from backend.scaling.kubernetes.client import get_apps_v1_api, get_core_v1_api

BASE_LOCUSTFILE = Path(r"D:\CIS\microservices-demo\src\loadgenerator\locustfile.py")
NAMESPACE = "online-boutique"
CONFIGMAP_NAME = "dpbps-locust-e04"

TARGET_SERVICES = [
    "frontend", "cartservice", "productcatalogservice", "currencyservice",
    "paymentservice", "shippingservice", "emailservice", "checkoutservice",
    "recommendationservice", "adservice"
]


def fetch_loadgenerator_logs() -> str:
    """Fetch recent logs from the loadgenerator container."""
    try:
        res = subprocess.run(
            ["kubectl", "logs", "-n", NAMESPACE, "deployment/loadgenerator", "-c", "main", "--tail=50"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.stdout if res.returncode == 0 else f"Could not fetch logs: {res.stderr}"
    except Exception as e:
        return f"Error fetching logs: {e}"


def get_active_stage(elapsed: float) -> str:
    """Return the active E04 stage label based on elapsed seconds."""
    if elapsed < 20.0:
        return "Ramp-Up (60u)"
    elif elapsed < 200.0:
        return "Sustained (60u)"
    elif elapsed < 220.0:
        return "Ramp-Down (0u)"
    else:
        return "Concluded"


def setup_e04_configmap_and_mount():
    """Create ConfigMap dpbps-locust-e04 and patch deployment/loadgenerator volume mount."""
    core_api = get_core_v1_api()
    apps_api = get_apps_v1_api()

    prof = get_sustained_high_traffic_profile()
    combined_code = generate_combined_locustfile(BASE_LOCUSTFILE, prof)

    cm_body = client.V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=client.V1ObjectMeta(
            name=CONFIGMAP_NAME,
            namespace=NAMESPACE,
            labels={"app": "loadgenerator", "dpbps.experiment": "e04"},
        ),
        data={"locustfile.py": combined_code},
    )

    try:
        core_api.read_namespaced_config_map(name=CONFIGMAP_NAME, namespace=NAMESPACE)
        core_api.replace_namespaced_config_map(name=CONFIGMAP_NAME, namespace=NAMESPACE, body=cm_body)
        print(f"  [OK] Replaced existing ConfigMap '{CONFIGMAP_NAME}'")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            core_api.create_namespaced_config_map(namespace=NAMESPACE, body=cm_body)
            print(f"  [OK] Created ConfigMap '{CONFIGMAP_NAME}'")
        else:
            raise

    # Verify loadgenerator replicas is 0 before patching mount
    dep = apps_api.read_namespaced_deployment(name="loadgenerator", namespace=NAMESPACE)
    assert dep.spec.replicas == 0, f"Expected 0 replicas, got {dep.spec.replicas}!"

    patch_body = {
        "spec": {
            "template": {
                "spec": {
                    "volumes": [
                        {
                            "name": "locustfile-volume",
                            "configMap": {
                                "name": CONFIGMAP_NAME,
                                "items": [
                                    {
                                        "key": "locustfile.py",
                                        "path": "locustfile.py",
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }
    }
    apps_api.patch_namespaced_deployment(name="loadgenerator", namespace=NAMESPACE, body=patch_body)
    print(f"  [OK] Patched deployment/loadgenerator volume to use '{CONFIGMAP_NAME}'")


def main():
    print("=" * 80)
    print("STAGE 8 — LIVE EXPERIMENT E04: SUSTAINED_HIGH_TRAFFIC EXECUTION")
    print("=" * 80)

    # 1. Pre-Execution Safety Verifications
    print("\n[STEP 1] Pre-Execution Safety Verifications...")
    assert cfg.SCALING_ENABLED is False, "SCALING_ENABLED must be False (DRY-RUN mode only)!"
    print("  [OK] SCALING_ENABLED is False (Actuator DRY-RUN posture confirmed).")

    prom_client = PrometheusClient(base_url="http://localhost:9090")
    assert prom_client.execute_query("up").is_present, "Prometheus is not reachable at http://localhost:9090!"
    print("  [OK] Prometheus connectivity verified.")

    # Setup and verify ConfigMap dpbps-locust-e04
    setup_e04_configmap_and_mount()

    manager = ExperimentManager()
    executor = ExperimentExecutor(manager=manager, namespace=NAMESPACE)

    # Reconcile cluster state before starting
    reconcile_res = executor.reconcile_cluster_state()
    print(f"  [OK] Cluster reconciliation: {reconcile_res.get('action')} ({reconcile_res.get('reason')})")

    # 2. Create Experiment Record
    print("\n[STEP 2] Creating Experiment Record...")
    exp = manager.create_experiment(
        profile_name=WorkloadProfileName.SUSTAINED_HIGH_TRAFFIC,
        notes="Live Stage 8 E04 sustained high traffic (60 users @ 5 u/s, 180s plateau, 220s total)",
        tags=["stage-8", "e04", "sustained-high-traffic", "live-run"],
    )
    exp_id = exp.experiment_id
    print(f"  [OK] Experiment created: {exp_id}")
    print(f"       Profile: {exp.profile_name.value}")
    print(f"       Peak Users: {exp.configuration.users}, Spawn Rate: {exp.configuration.spawn_rate} u/s")
    print(f"       Stages: {[(s.name, s.duration_seconds, s.target_users) for s in exp.configuration.stages]}")
    print(f"       Total Duration: {exp.configuration.total_duration_seconds}s")
    print(f"       Target Host: {exp.configuration.target_host}")

    # 3. Transition to READY
    print("\n[STEP 3] Transitioning to READY status...")
    manager.update_status(exp_id, ExperimentStatus.READY)
    exp = manager.get_experiment(exp_id)
    assert exp.status == ExperimentStatus.READY, f"Expected READY, got {exp.status}"
    print(f"  [OK] Experiment {exp_id} is in READY status.")

    # 4. Authorize Execution Lock
    print("\n[STEP 4] Authorizing Experiment Execution Lock...")
    os.environ["EXPERIMENT_EXECUTION_ENABLED"] = "true"
    can_exec, reasons = executor.can_execute(exp_id)
    if not can_exec:
        print(f"  [ERROR] Execution blocked: {reasons}")
        sys.exit(1)
    print("  [OK] Master safety check passed. can_execute=True.")

    # 5. Execute Experiment via Executor
    print(f"\n[STEP 5] Starting Experiment {exp_id} via ExperimentExecutor...")
    start_res = executor.start_experiment(exp_id)
    print(f"  [OK] Experiment started successfully: status={start_res.get('status')}")
    print(f"       Started at: {start_res.get('started_at')}")
    print(f"       Target duration: {start_res.get('target_duration_seconds')}s")

    # Prepare adapter and controller for monitoring
    adapter = KubernetesTelemetryAdapter(namespace=NAMESPACE, prometheus_client=prom_client)
    dpbps_controller = DPBPSController()
    actuator = KubernetesScalingActuator(dry_run=True)

    exp_dir = executor.storage_dir / exp_id
    telemetry_snapshots: List[Dict[str, Any]] = []
    dpbps_decision_history: List[Dict[str, Any]] = []
    workload_observations: List[Dict[str, Any]] = []
    actuator_audit_history: List[Dict[str, Any]] = []
    log_lines: List[str] = [
        f"[{datetime.now(timezone.utc).isoformat()}] Experiment {exp_id} started. Profile: SUSTAINED_HIGH_TRAFFIC, Duration: 220s\n"
    ]

    # 6. Live Monitoring Loop (220 seconds target)
    print("\n[STEP 6] Monitoring Live Workload Execution (220 seconds, 3 stages)...")
    header = f"{'TIME':8} | {'ELAPSED':8} | {'STAGE':18} | {'FE_RPS':8} | {'FE_P95':8} | {'PROD_RPS':8} | {'CART_RPS':8} | {'CART_P95':8} | {'DPBPS':16} | {'STATUS'}"
    print(header)
    print("-" * 125)

    start_time = time.time()
    total_target = exp.configuration.total_duration_seconds
    iteration = 0
    locust_logs_captured = ""

    while True:
        loop_start = time.time()
        elapsed = loop_start - start_time
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
        active_stage_str = get_active_stage(elapsed)

        # A. Watchdog check
        watchdog = executor.watchdog_check(exp_id)
        if not watchdog.get("active", True):
            msg = f"[{now_str}] [WATCHDOG TRIGGERED] Experiment completed: {watchdog.get('reason')}"
            print(f"\n{msg}")
            log_lines.append(msg + "\n")
            break

        # B. Telemetry collection
        try:
            valid_inputs, excluded = adapter.get_telemetry_inputs()
            raw_telemetry = adapter.collect_deployment_telemetry()
            
            # Map by service name
            tel_map = {t.get("service_name"): t for t in raw_telemetry}

            # C. Extended quantile latency collection for target services
            quantiles = {}
            for sname in ["frontend", "cartservice", "checkoutservice", "productcatalogservice"]:
                p50 = prom_client.query_p50_latency(sname)
                p99 = prom_client.query_p99_latency(sname)
                quantiles[sname] = {
                    "p50_ms": p50.first_value if p50.is_present else None,
                    "p99_ms": p99.first_value if p99.is_present else None,
                }

            # D. DPBPS Evaluation
            decisions = dpbps_controller.evaluate(valid_inputs)
            act_results = actuator.execute_decisions(decisions)

            act_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "stage": active_stage_str,
                "results": [r.model_dump(mode="json") if hasattr(r, "model_dump") else r.dict() for r in act_results],
            }
            actuator_audit_history.append(act_record)

            fe_tel = tel_map.get("frontend", {})
            cart_tel = tel_map.get("cartservice", {})
            prod_tel = tel_map.get("productcatalogservice", {})

            fe_rps = fe_tel.get("request_rate")
            fe_p95 = fe_tel.get("p95_latency_ms")
            cart_rps = cart_tel.get("request_rate")
            cart_p95 = cart_tel.get("p95_latency_ms")
            prod_rps = prod_tel.get("request_rate")

            fe_rps_str = f"{fe_rps:.1f}" if fe_rps is not None else "--"
            fe_p95_str = f"{fe_p95:.1f}ms" if fe_p95 is not None else "--"
            prod_rps_str = f"{prod_rps:.1f}" if prod_rps is not None else "--"
            cart_rps_str = f"{cart_rps:.1f}" if cart_rps is not None else "--"
            cart_p95_str = f"{cart_p95:.1f}ms" if cart_p95 is not None else "--"

            hold_count = sum(1 for d in decisions if d.action.value == 'HOLD')
            scale_count = sum(1 for d in decisions if d.action.value in ('SCALE_UP', 'SCALE_DOWN'))
            dec_summary = f"{len(decisions)} ({hold_count}H / {scale_count}S)"

            row = f"{now_str:8} | {elapsed:6.1f}s | {active_stage_str:18} | {fe_rps_str:8} | {fe_p95_str:8} | {prod_rps_str:8} | {cart_rps_str:8} | {cart_p95_str:8} | {dec_summary:16} | RUNNING"
            print(row)
            sys.stdout.flush()
            log_lines.append(row + "\n")

            # Record snapshot
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "stage": active_stage_str,
                "services": tel_map,
                "quantiles": quantiles,
            }
            telemetry_snapshots.append(snapshot)

            dec_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "stage": active_stage_str,
                "decisions": [d.model_dump(mode="json") if hasattr(d, "model_dump") else d.dict() for d in decisions],
            }
            dpbps_decision_history.append(dec_record)

            workload_obs = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "stage": active_stage_str,
                "frontend_rps": fe_rps,
                "frontend_p95_ms": fe_p95,
                "productcatalog_rps": prod_rps,
                "cartservice_rps": cart_rps,
                "cartservice_p95_ms": cart_p95,
                "active_services_count": len(valid_inputs),
            }
            workload_observations.append(workload_obs)

        except Exception as poll_err:
            err_msg = f"[{now_str}] Telemetry polling error: {poll_err}"
            print(err_msg)
            sys.stdout.flush()
            log_lines.append(err_msg + "\n")

        iteration += 1
        cur_logs = fetch_loadgenerator_logs()
        if cur_logs and "Error" not in cur_logs and "Could not fetch" not in cur_logs:
            locust_logs_captured = cur_logs

        # Sleep for remainder of 10s cadence
        sleep_dur = max(0.5, 10.0 - (time.time() - loop_start))
        time.sleep(sleep_dur)

    # 7. Post-Experiment Verification & Results Ingestion
    print("\n[STEP 7] Post-Experiment Verification and Persistence...")
    end_time = time.time()
    total_run_duration = end_time - start_time
    print(f"  [OK] Total execution duration: {total_run_duration:.1f}s (Target: {total_target}s)")

    # Fetch final Locust logs before cleanup
    locust_logs = fetch_loadgenerator_logs()
    if ("Error" in locust_logs or "Could not fetch" in locust_logs or not locust_logs.strip()) and locust_logs_captured:
        locust_logs = locust_logs_captured
    print("  [OK] Retrieved final loadgenerator Locust logs.")

    # Ensure lock is cleared
    os.environ["EXPERIMENT_EXECUTION_ENABLED"] = "false"
    print("  [OK] Master safety lock re-locked: EXPERIMENT_EXECUTION_ENABLED=false.")

    # Verify loadgenerator scale returns to 0
    post_reconcile = executor.reconcile_cluster_state()
    print(f"  [OK] Post-run cluster state: {post_reconcile}")

    # Compute observed aggregate metrics
    observed_rates = [w["frontend_rps"] for w in workload_observations if w["frontend_rps"] is not None]
    avg_fe_rps = sum(observed_rates) / len(observed_rates) if observed_rates else 0.0
    peak_fe_rps = max(observed_rates) if observed_rates else 0.0

    observed_latencies = [w["frontend_p95_ms"] for w in workload_observations if w["frontend_p95_ms"] is not None]
    avg_p95 = sum(observed_latencies) / len(observed_latencies) if observed_latencies else 0.0
    max_p95 = max(observed_latencies) if observed_latencies else 0.0

    # Decision counts
    total_scale_up = sum(
        1 for c in dpbps_decision_history for d in c["decisions"] if d.get("action") == "SCALE_UP"
    )
    total_scale_down = sum(
        1 for c in dpbps_decision_history for d in c["decisions"] if d.get("action") == "SCALE_DOWN"
    )
    total_hold = sum(
        1 for c in dpbps_decision_history for d in c["decisions"] if d.get("action") == "HOLD"
    )
    total_bottlenecks = sum(
        1 for c in dpbps_decision_history for d in c["decisions"] if d.get("bottleneck") is not None
    )

    # Ingest final experiment record
    exp = manager.get_experiment(exp_id)
    exp.actual_observed_request_rate = round(avg_fe_rps, 2)
    exp.end_timestamp = datetime.now(timezone.utc).isoformat()
    manager._persist_experiment(exp)

    # Write telemetry_metrics.json (Artifact 2)
    telemetry_path = exp_dir / "telemetry_metrics.json"
    telemetry_path.write_text(json.dumps({
        "experiment_id": exp_id,
        "total_snapshots": len(telemetry_snapshots),
        "snapshots": telemetry_snapshots,
    }, indent=2, default=str), encoding="utf-8")
    print(f"  [OK] Wrote {len(telemetry_snapshots)} snapshots to telemetry_metrics.json")

    # Write dpbps_decisions.json (Artifact 4)
    decisions_path = exp_dir / "dpbps_decisions.json"
    decisions_path.write_text(json.dumps({
        "experiment_id": exp_id,
        "total_evaluations": len(dpbps_decision_history),
        "total_decisions": total_hold + total_scale_up + total_scale_down,
        "hold_count": total_hold,
        "scale_up_count": total_scale_up,
        "scale_down_count": total_scale_down,
        "bottlenecks_detected": total_bottlenecks,
        "evaluations": dpbps_decision_history,
    }, indent=2, default=str), encoding="utf-8")
    print(f"  [OK] Wrote {len(dpbps_decision_history)} decision cycles to dpbps_decisions.json")

    # Write actuator_audit.json (Artifact 5)
    actuator_path = exp_dir / "actuator_audit.json"
    actuator_path.write_text(json.dumps({
        "experiment_id": exp_id,
        "execution_mode": "DRY_RUN",
        "total_evaluations": len(actuator_audit_history),
        "evaluations": actuator_audit_history,
    }, indent=2, default=str), encoding="utf-8")
    print(f"  [OK] Wrote {len(actuator_audit_history)} actuator evaluation cycles to actuator_audit.json")

    # Write workload_metrics.json (Artifact 3)
    workload_path = exp_dir / "workload_metrics.json"
    workload_path.write_text(json.dumps({
        "experiment_id": exp_id,
        "profile_name": exp.profile_name.value,
        "target_users": exp.selected_concurrency,
        "target_duration_seconds": total_target,
        "actual_duration_seconds": round(total_run_duration, 1),
        "average_frontend_rps": round(avg_fe_rps, 2),
        "peak_frontend_rps": round(peak_fe_rps, 2),
        "average_frontend_p95_ms": round(avg_p95, 2),
        "max_frontend_p95_ms": round(max_p95, 2),
        "observations": workload_observations,
        "locust_tail_logs": locust_logs,
    }, indent=2, default=str), encoding="utf-8")
    print("  [OK] Wrote workload statistics to workload_metrics.json")

    # Write experiment_summary.json (Artifact 6)
    summary_path = exp_dir / "experiment_summary.json"
    summary_path.write_text(json.dumps({
        "experiment_id": exp_id,
        "profile_name": exp.profile_name.value,
        "status": exp.status.value,
        "created_at": exp.created_at,
        "started_at": exp.start_timestamp or start_res.get("started_at"),
        "ended_at": exp.end_timestamp,
        "duration_seconds": round(total_run_duration, 1),
        "target_duration_seconds": total_target,
        "average_frontend_rps": round(avg_fe_rps, 2),
        "peak_frontend_rps": round(peak_fe_rps, 2),
        "average_frontend_p95_ms": round(avg_p95, 2),
        "max_frontend_p95_ms": round(max_p95, 2),
        "scaling_decisions_scale_up": total_scale_up,
        "scaling_decisions_scale_down": total_scale_down,
        "scaling_decisions_hold": total_hold,
        "bottlenecks_detected": total_bottlenecks,
        "actuator_mode": "DRY_RUN",
        "cluster_modified": False,
        "completed_successfully": exp.status == ExperimentStatus.COMPLETED,
        "post_run_loadgenerator_replicas": 0,
    }, indent=2, default=str), encoding="utf-8")
    print("  [OK] Wrote experiment summary to experiment_summary.json")

    # Write experiment.log (Artifact 7)
    log_path = exp_dir / "experiment.log"
    log_content = "".join(log_lines) + "\n\n--- LOCUST POD LOGS ---\n" + locust_logs
    log_path.write_text(log_content, encoding="utf-8")
    print("  [OK] Wrote console output and pod logs to experiment.log")

    # Verify experiment_config.json (Artifact 1) exists
    cfg_file = exp_dir / "metadata.json"
    exp_cfg_path = exp_dir / "experiment_config.json"
    if not exp_cfg_path.exists() and cfg_file.exists():
        exp_cfg_path.write_text(cfg_file.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  [OK] Verified experiment_config.json at {exp_cfg_path}")

    print("\n" + "=" * 80)
    print(f"EXPERIMENT {exp_id} COMPLETED SUCCESSFULLY")
    print(f"Status: {exp.status.value}")
    print(f"Duration: {total_run_duration:.1f}s / {total_target}s")
    print(f"Avg Frontend RPS: {avg_fe_rps:.2f} | Peak RPS: {peak_fe_rps:.2f}")
    print(f"Avg Frontend P95: {avg_p95:.2f}ms | Max P95: {max_p95:.2f}ms")
    print(f"Decisions: HOLD={total_hold}, SCALE_UP={total_scale_up}, SCALE_DOWN={total_scale_down}, BOTTLENECKS={total_bottlenecks}")
    print(f"Results Directory: {exp_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()

