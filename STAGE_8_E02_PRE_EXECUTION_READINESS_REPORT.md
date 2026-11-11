# STAGE 8 — EXPERIMENT E02: PRE-EXECUTION READINESS REPORT
## Workload Verification, Safety Audit, and Execution Readiness for GRADUAL_TRAFFIC_INCREASE

**Project Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Algorithm:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Next Experiment:** E02 (`GRADUAL_TRAFFIC_INCREASE`)  
**Target Workload:** Google Cloud Online Boutique (`online-boutique` namespace)  
**Host Environment:** Windows 11 Enterprise | Docker Desktop Kubernetes (`docker-desktop`)  
**Safety Status:** Live scaling strictly DISABLED (`SCALING_ENABLED=false`) | Actuator in DRY-RUN mode  
**Readiness Verdict:** **CONDITIONAL GO** (Readiness confirmed; requires multi-stage load synchronization authorization)

---

## 1. E01 Raw Result Validation Summary

Experiment E01 (`NORMAL_TRAFFIC`) was executed on 2026-11-10T15:24:25Z and successfully concluded after 140.0 seconds. All raw records in `results/experiments/exp_20261110T152425_normal_traffic_838109a5/` were audited against the reported metrics:

- **Frontend Ingress Throughput:**
  - Observed Average: **5.78 req/s** (5.7759 req/s raw)
  - Observed Peak: **10.31 req/s** (10.3078 req/s raw)
- **ProductCatalog Throughput (Downstream Fan-out):**
  - Observed Peak: **54.29 req/s** (54.2905 req/s raw at Snapshot 12)
  - Steady-State Average: **30.56 req/s** ($> 5\times$ amplification over frontend)
- **Latency Characterization:**
  - Steady-State P50: **18.95 ms – 20.30 ms**
  - Steady-State P95: **90.49 ms – 119.09 ms** (well below 200 ms SLA target)
  - Steady-State P99: **195.83 ms – 223.82 ms**
  - Early Transient Warm-Up Peak ($t=50\text{s}$): 1,360.97 ms (JIT & gRPC connection pooling)
- **Error Rates:** **0.000%** across all 10 microservices (zero 5xx HTTP errors, zero gRPC failures).
- **Resource Footprint:**
  - Peak Frontend CPU: 34.93% (34.9m / 100m)
  - Cartservice Memory: 64.4 MiB / 64 MiB request (100.7%, well below 128 MiB limit)
  - Node Headroom: > 94% CPU and > 80% RAM available on Docker Desktop control-plane.
- **Artifact Authenticity:** All 8 storage artifacts (`experiment_config.json`, `telemetry_metrics.json`, `workload_metrics.json`, `dpbps_decisions.json`, `actuator_audit.json`, `experiment_summary.json`, `experiment.log`, `metadata.json`) are validated and intact.

---

## 2. E01 Decision Analysis

The DPBPS controller performed 14 continuous evaluation cycles during E01, generating **108 individual service-level scaling decisions**:

```
+-----------------------------------------------------------------------------+
|                          DPBPS DECISION AUDIT SUMMARY                       |
+------------------------------+-------+------------+-------------------------+
| Decision Action              | Count | Percentage | Outcome Category        |
+------------------------------+-------+------------+-------------------------+
| HOLD                         |   107 |      99.1% | Pressure within bounds  |
| SCALE_UP                     |     1 |       0.9% | Transient P95 warmup    |
| SCALE_DOWN                   |     0 |       0.0% | Min replicas bound (=1) |
| INSUFFICIENT_TELEMETRY       |     0 |       0.0% | Zero stale samples      |
+------------------------------+-------+------------+-------------------------+
| TOTAL EVALUATED              |   108 |     100.0% | 10 Microservices        |
+------------------------------+-------+------------+-------------------------+
```

### Deep Dive: Cycle 4 SCALE_UP Decision
- **Timestamp / Elapsed:** 2026-11-10T15:25:07Z ($t = 40.0\text{s}$).
- **Target Deployment:** `frontend` (Namespace: `online-boutique`).
- **Telemetry Drivers:** Ingress RPS surged to $2.0\text{ req/s}$; tail P95 latency surged to $971.13\text{ ms}$ ($> 200\text{ ms}$ SLA target).
- **Mathematical Pressure Score:**
  $$\text{Latency Pressure} = \frac{971.13 - 200.0}{200.0} = 3.8556$$
  $$\text{Aggregate Score} = 0.30 \times 3.8556 = 1.1567 \quad (> 0.20 \text{ threshold})$$
- **Decision:** `requested_replicas = 2` (Action: `SCALE_UP`).
- **Bottleneck Classification:** `frontend` (Highest pressure leaf in tree).
- **Actuator Validation:** Mode was `DRY_RUN`. The actuator passed all 11 safety rules and logged status **`VALIDATED`**. Zero cluster mutation occurred (`cluster_modified: false`).
- **Self-Stabilization:** By $t=60\text{s}$, connection pools stabilized, P95 dropped to $315\text{ ms} \to 90\text{ ms}$, and decisions returned to `HOLD`.

---

## 3. E01 Data Discrepancies and Explanations

| Observed Discrepancy | Apparent Contradiction | Technical Explanation / Root Cause |
|---|---|---|
| **14 cycles vs. 108 decisions** | Expected 14 decisions, found 108 | DPBPS evaluates at **per-microservice granularity**, not cluster-level. Polling evaluated active services on each tick: 3 services in ticks 0–2 ($3 \times 3 = 9$), 5 in tick 3, 6 in tick 4, 8 in tick 5, and 10 in ticks 6–13 ($8 \times 10 = 80$). Total: $9 + 5 + 6 + 8 + 80 = 108$. |
| **107 HOLD and 1 SCALE_UP** | Nominal traffic expected only HOLD | The single `SCALE_UP` was an authentic dynamic response to cold-start gRPC connection establishment at $t=40\text{s}$, demonstrating high sensitivity to SLA violations. |
| **130s target vs. 140s actual** | Execution duration was 10s longer | In `executor.py`, `watchdog_check()` enforces a 5s grace period ($130 + 5 = 135\text{s}$). On the discrete 10s monitoring tick, $t=130\text{s} < 135\text{s}$ (did not trip), and $t=140.1\text{s} \ge 135\text{s}$ (triggered termination). |

---

## 4. E02 Workload Configuration Verification

The authoritative profile definition was inspected in [`backend/workload/profiles.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/profiles.py#L70-L115):

```python
def get_gradual_traffic_increase_profile() -> WorkloadProfileConfig:
    """Profile 2: GRADUAL_TRAFFIC_INCREASE – Evaluate progressive scaling response."""
    return WorkloadProfileConfig(
        profile_name=WorkloadProfileName.GRADUAL_TRAFFIC_INCREASE,
        display_name="Profile 2: Gradual Traffic Increase (Stepped)",
        target_host="frontend:80",
        users=50,
        spawn_rate=2.0,
        ramp_up_seconds=10,
        steady_state_seconds=160,
        ramp_down_seconds=10,
        total_duration_seconds=180,
        stages=[
            WorkloadStage(stage_index=0, name="Step 1: Low Concurrency", target_users=10, duration_seconds=60, spawn_rate=2.0),
            WorkloadStage(stage_index=1, name="Step 2: Moderate Concurrency", target_users=25, duration_seconds=60, spawn_rate=2.0),
            WorkloadStage(stage_index=2, name="Step 3: High Concurrency", target_users=50, duration_seconds=60, spawn_rate=2.0),
        ],
    )
```

### Reconciliation with Specification:
- **Experiment:** E02
- **Profile Name:** `GRADUAL_TRAFFIC_INCREASE`
- **Initial Users:** 10 (Stage 1, 0–60s)
- **Intermediate Users:** 25 (Stage 2, 60–120s)
- **Maximum Users:** 50 (Stage 3, 120–180s)
- **Spawn Rate:** 2.0 users/sec (Constant across all step transitions)
- **Stage Durations:** 60s, 60s, 60s
- **Total Duration:** **180 seconds** ($60 + 60 + 60$)
- **Watchdog Timeout:** **185 seconds** ($180 + 5$ grace window)
- **Safety Invariant:** Validated by `validate_workload_config()`.

---

## 5. E02 Locust Shape Verification

The programmatic stage generator [`backend/workload/shape_generator.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/shape_generator.py) was executed against the E02 profile:

### Generated Stage Sequence:
```python
stages = [
    {"duration": 60,  "users": 10, "spawn_rate": 2.0, "name": "Step 1: Low Concurrency"},
    {"duration": 120, "users": 25, "spawn_rate": 2.0, "name": "Step 2: Moderate Concurrency"},
    {"duration": 180, "users": 50, "spawn_rate": 2.0, "name": "Step 3: High Concurrency"},
]
```

### Tick Progression Logic:
- $0 \le t < 60\text{s}$: Returns `(10, 2.0)` $\to$ Ramps to 10 users in 5s, holds steady for 55s.
- $60 \le t < 120\text{s}$: Returns `(25, 2.0)` $\to$ Ramps $+15$ users in 7.5s (to 25), holds steady for 52.5s.
- $120 \le t < 180\text{s}$: Returns `(50, 2.0)` $\to$ Ramps $+25$ users in 12.5s (to 50), holds peak for 47.5s.
- $t \ge 180\text{s}$: Returns `None` $\to$ Signals Locust to gracefully conclude user sessions.

Syntactic validity and compilation confirmed via `test_locust_shape_generator_code()`.

---

## 6. Live Infrastructure Health Audit

A comprehensive live probe was executed across the Kubernetes cluster and monitoring plane on 2026-11-10T21:13:10+05:30:

```
+-----------------------------------------------------------------------------+
|                        LIVE CLUSTER INFRASTRUCTURE PROBE                    |
+------------------------+---------------+--------------+---------------------+
| Component              | Pod / Service | Status       | Notes / Metrics     |
+------------------------+---------------+--------------+---------------------+
| Docker Desktop Engine  | v29.3.1 (WSL2)| Running      | 12 Engine Containers|
| Kubernetes Node        | desktop-ctrl  | Ready        | v1.34.3 Node Ready  |
| Metrics Server         | v0.8.0        | Active       | v1beta1 API True    |
| Prometheus Server      | :9090         | UP (HTTP 200)| 19 Scrape Targets   |
| Grafana Dashboard      | :3000         | UP (HTTP 200)| Database: OK        |
| OpenTelemetry Collector| :8889         | UP (HTTP 200)| Active scrape target|
+------------------------+---------------+--------------+---------------------+
| frontend               | 1/1 Running   | Ready        | Restarts: 0         |
| cartservice            | 1/1 Running   | Ready        | Restarts: 0         |
| productcatalogservice  | 1/1 Running   | Ready        | Restarts: 0         |
| currencyservice        | 1/1 Running   | Ready        | Restarts: 0         |
| paymentservice         | 1/1 Running   | Ready        | Restarts: 0         |
| shippingservice        | 1/1 Running   | Ready        | Restarts: 0         |
| emailservice           | 1/1 Running   | Ready        | Restarts: 0         |
| checkoutservice        | 1/1 Running   | Ready        | Restarts: 0         |
| recommendationservice  | 1/1 Running   | Ready        | Restarts: 0         |
| adservice              | 1/1 Running   | Ready        | Restarts: 0         |
| redis-cart             | 1/1 Running   | Ready        | Protected Infra     |
| opentelemetrycollector | 1/1 Running   | Ready        | Protected Infra     |
| loadgenerator          | 0/0 Replicas  | Scaled Zero  | Clean Idle Baseline |
+------------------------+---------------+--------------+---------------------+
```

All 10 application microservices + Redis + OTel collector are 1/1 Ready with zero container restarts.

---

## 7. Experiment Safety Verification

All execution guardrails were inspected directly against the runtime environment:

1. **Live Scaling Actuator Mode:** `cfg.SCALING_ENABLED == False` (Enforced).
2. **Actuator Posture:** Strict **`DRY_RUN`** mode only.
3. **Master Safety Lock:** `EXPERIMENT_EXECUTION_ENABLED` is unset/`None` in environment (Strictly locked).
4. **Active Experiments:** 0 experiments in `RUNNING` status.
5. **Concurrency Lock:** `active_experiment_id == None`.
6. **Cluster Reconciliation:** `reconcile_cluster_state()` returned `action: "none"`, confirming `loadgenerator` is already at 0 replicas.
7. **Emergency Stop:** Verified operational via `executor.emergency_stop()`.

---

## 8. Automated Test Results

The full suite of relevant workload, executor, watchdog, and DPBPS high-traffic tests was executed:

```bash
$ python -m pytest backend/tests/test_workload_and_experiments.py backend/tests/test_dpbps_high_traffic.py -v
======================= 40 passed, 22 warnings in 0.60s =======================
```

- **Workload Profile Tests:** 7 passed (`test_all_six_profiles_exist`, `test_profile_fields_and_stages_complete`).
- **Locust Shape Generator Tests:** 2 passed (`test_locust_shape_generator_stages`, `test_locust_shape_generator_code`).
- **Experiment Manager Tests:** 8 passed (`test_valid_state_transitions`, `test_running_transition_strictly_forbidden`).
- **Experiment Executor Tests:** 6 passed (`test_executor_start_experiment_blocked_by_safety_lock`, `test_executor_watchdog_duration_expiry`).
- **Emergency Stop & Safety Tests:** 4 passed (`test_experiment_executor_emergency_stop`, `test_api_safety_check_and_emergency_stop`).
- **High-Traffic DPBPS Tests:** 7 passed (`test_synthetic_e03_sudden_traffic_spike_behavior`, `test_synthetic_downstream_bottleneck_isolation`).
- **Full Backend Regression Suite:** **162 passed, 2 skipped, 0 failures** in 6.66s.

---

## 9. Outstanding Risks and Mitigation Plan

| Risk Factor | Impact / Severity | Mitigation Strategy |
|---|---|---|
| **Stepped Concurrency Delivery in Pod** | Medium: Stock `loadgenerator` image uses static env vars `USERS` and `RATE`. If launched with `USERS=50`, it would generate 50 users immediately rather than stepping 10 $\to$ 25 $\to$ 50. | **Mitigation:** The E02 execution supervisor script will either dynamically patch the `loadgenerator` user target at $t=60\text{s}$ (to 25) and $t=120\text{s}$ (to 50), or mount `DPBPSWorkloadShape` into the container via ConfigMap before starting traffic. |
| **ProductCatalog High Fan-Out Under 50 Users** | Medium: At 10 users, `productcatalogservice` experienced 54.3 req/s ($5.4\times$). At 50 users, request rates may exceed 250 req/s. | **Mitigation:** Expected research phenomenon; DPBPS bottleneck detection will evaluate whether leaf saturation propagates upstream. Actuator remains in DRY-RUN mode. |
| **Cartservice Memory Limit** | Low: Cartservice consumed 64.4 MiB (100.7% of 64 MiB request) during E01. Under 50 users, heap allocation will grow. | **Mitigation:** Container limit is 128 MiB (50% headroom remaining). If usage exceeds 100 MiB, DPBPS memory pressure scoring will trigger a simulated scale-up. |

---

## 10. Final Readiness Verdict

### **VERDICT: CONDITIONAL GO**

#### Conditions Required Prior to Initiating E02:
1. Operator authorization to proceed from Stage 8 E01 validation to E02 execution.
2. Selection of stepped concurrency delivery method (Supervisor runtime env patching at $t=60\text{s}/120\text{s}$ vs. `DPBPSWorkloadShape` ConfigMap mount).
3. Preservation of all safety constraints: `SCALING_ENABLED=false` (DRY-RUN), watchdog timeout at 185s, and automatic scale-to-zero upon completion.

**Execution has halted. All systems are primed, validated, and awaiting operator instruction.**

