# STAGE 8 — EXPERIMENT E02: FINAL PRE-EXECUTION READINESS REPORT
## Workload Verification, Infrastructure Audit, and Final Authorization Gate for GRADUAL_TRAFFIC_INCREASE

**Project Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Algorithm:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Workload Experiment:** E02 — `GRADUAL_TRAFFIC_INCREASE`  
**Target Cluster:** Single-Node Kubernetes control-plane (`docker-desktop`)  
**Application Namespace:** `online-boutique` | **Monitoring Namespace:** `monitoring`  
**Execution Posture:** Live scaling strictly DISABLED (`SCALING_ENABLED=false`) | Actuator in DRY-RUN mode  
**Loadgenerator Scale:** Strictly **0 / 0 replicas** (0 pods scheduled)  
**Final Readiness Verdict:** **GO (READY FOR OPERATOR AUTHORIZATION)**

---

## 1. Executive Summary

This report establishes the final pre-execution verification for **Experiment E02 (`GRADUAL_TRAFFIC_INCREASE`)**. Following the approval of the ConfigMap-based `LoadTestShape` injection mechanism, the cluster infrastructure, monitoring stack, ConfigMap integration, and safety controllers were probed and validated.

All safety requirements have been strictly enforced:
- Zero live workload traffic was generated.
- `loadgenerator` replicas remains at **0**.
- `SCALING_ENABLED` is `false` (DRY-RUN mode only).
- `EXPERIMENT_EXECUTION_ENABLED` is locked (`false`).
- All E01 experiment records are preserved untouched.
- Full backend regression suite: **166 passed, 2 skipped, 0 failures** (6.79s).

---

## 2. Infrastructure Health Status (TASK 1)

A complete live probe of the Kubernetes cluster, monitoring plane, and application microservices was conducted on **2026-11-10T22:04:57+05:30**:

```
+-----------------------------------------------------------------------------+
|                      LIVE CLUSTER INFRASTRUCTURE MATRIX                     |
+------------------------+---------------+--------------+---------------------+
| Component              | Pod / Context | Live Status  | Resource / Details  |
+------------------------+---------------+--------------+---------------------+
| Docker Desktop Engine  | v29.3.1 (WSL2)| Running      | 12 Engine Containers|
| Kubernetes Node        | desktop-ctrl  | Ready        | v1.34.3 Node Ready  |
| Metrics Server         | v0.8.0        | Active       | v1beta1 API True    |
| Prometheus Server      | :9090         | UP (HTTP 200)| 19 Scrape Targets   |
| Grafana Dashboard      | :3000         | UP (HTTP 200)| Database: OK        |
| OpenTelemetry Collector| :8889         | UP (HTTP 200)| Active scrape target|
+------------------------+---------------+--------------+---------------------+
| frontend               | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| cartservice            | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| productcatalogservice  | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| currencyservice        | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| paymentservice         | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| shippingservice        | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| emailservice           | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| checkoutservice        | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| recommendationservice  | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| adservice              | 1/1 Running   | Ready        | Restarts: 0 (130m)  |
| redis-cart (Infra)     | 1/1 Running   | Ready        | Protected Infra     |
| opentelemetrycollector | 1/1 Running   | Ready        | Protected Infra     |
| loadgenerator          | 0/0 Replicas  | Scaled Zero  | 0 Pods Scheduled    |
+------------------------+---------------+--------------+---------------------+
```

- **Cluster Health:** 10/10 application deployments are `1/1 Ready`.
- **Node Capacity Headroom:** > 94% CPU headroom and > 80% RAM headroom available for the 50-user peak.
- **Monitoring Health:** Prometheus client queries (`up`) return `True`; Metrics Server provides pod metrics on `:4443`.

---

## 3. ConfigMap & Locust Integration Verification (TASK 2)

The multi-stage concurrency injection mechanism was constructed and verified in the live cluster while maintaining `loadgenerator` at 0 replicas:

### 3.1 ConfigMap `dpbps-locust-e02`
- **Namespace:** `online-boutique`
- **Labels:** `app: loadgenerator`, `dpbps.experiment: e02`
- **Data Key:** `locustfile.py` (3,439 bytes)
- **Contents:** Combines the standard Online Boutique user behaviors (`WebsiteUser`, `UserBehavior` with browsing, cart additions, currency updates, and checkout tasks) with the programmatic `DPBPSWorkloadShape`.

### 3.2 Deployment Volume & Mount Verification
The `loadgenerator` Deployment spec in Kubernetes was inspected via `kubectl get deployment loadgenerator -n online-boutique -o yaml`:
```yaml
spec:
  replicas: 0
  template:
    spec:
      volumes:
      - name: locustfile-volume
        configMap:
          name: dpbps-locust-e02
          items:
          - key: locustfile.py
            path: locustfile.py
      containers:
      - name: main
        volumeMounts:
        - name: locustfile-volume
          mountPath: /loadgen/locustfile.py
          subPath: locustfile.py
        securityContext:
          readOnlyRootFilesystem: true
```
- **Read-Only Compatibility:** The ConfigMap subPath volume mount is read-only and complies with `readOnlyRootFilesystem: true`.
- **Zero-Restart Guarantee:** The volume mount is bound at pod launch. The Locust process boots with the shape pre-loaded and executes all three stages in a single continuous process.

### 3.3 Entrypoint and Class Precedence
- **Entrypoint:** `locust --host="http://${FRONTEND_ADDR}" --headless -u "${USERS:-10}" -r "${RATE:-1}" 2>&1`
- **Precedence Verification:** Locust source code (`locust/main.py:384-389, 568-571`) confirms that `DPBPSWorkloadShape` takes complete precedence over `-u` and `-r`. CLI flags do not restrict concurrency.

---

## 4. E02 Workload Configuration Verification

Authoritative profile parameters from [`backend/workload/profiles.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/profiles.py#L70):

```
+-----------------------------------------------------------------------------+
|                      E02 WORKLOAD STAGES & CONCURRENCY                      |
+-------+-----------------------------+----------+------------+---------------+
| Stage | Stage Name                  | Duration | User Count | Spawn Rate    |
+-------+-----------------------------+----------+------------+---------------+
| 1     | Step 1: Low Concurrency     |   60s    | 10 users   | 2.0 users/sec |
| 2     | Step 2: Moderate Concurrency|   60s    | 25 users   | 2.0 users/sec |
| 3     | Step 3: High Concurrency    |   60s    | 50 users   | 2.0 users/sec |
+-------+-----------------------------+----------+------------+---------------+
| TOTAL | Workload Execution Window   |  180s    | Peak: 50   | Rate: 2.0 u/s |
| WATCH | Safety Watchdog Termination |  185s    | Timeout    | Auto Scale-0  |
+-------+-----------------------------+----------+------------+---------------+
```

### Concurrency Stepping Mathematics:
- **Stage 1 (0 to 60s):** $0 \to 10$ users in $10 / 2.0 = 5.0\text{s}$ ramp $\to 55.0\text{s}$ steady baseline.
- **Stage 2 (60 to 120s):** $10 \to 25$ users ($+15$ users) in $15 / 2.0 = 7.5\text{s}$ ramp $\to 52.5\text{s}$ steady baseline.
- **Stage 3 (120 to 180s):** $25 \to 50$ users ($+25$ users) in $25 / 2.0 = 12.5\text{s}$ ramp $\to 47.5\text{s}$ peak saturation.
- **$t \ge 180\text{s}$:** `tick()` returns `None`, concluding user sessions.
- **$t \ge 185\text{s}$:** Watchdog invokes automated scale-to-zero.

---

## 5. Experiment Safety Interlock Verification (TASK 3)

| Safety Guardrail | Verified Setting | Inspection Method | Status |
|---|---|---|---|
| **Active Experiments** | 0 RUNNING | `mgr.list_experiments()` | **LOCKED** |
| **Concurrency Lock** | `active_experiment_id == None` | `executor.active_experiment_id` | **CLEAR** |
| **Loadgenerator Replicas** | **0 / 0** | `kubectl get deployment loadgenerator` | **ZERO** |
| **Orphaned Pods** | **0 pods** | `kubectl get pods -l app=loadgenerator` | **ZERO** |
| **Actuator Operating Mode**| **DRY-RUN** | `cfg.SCALING_ENABLED == False` | **ENFORCED** |
| **Cluster Scaling Interlock**| Live scaling disabled | Actuator `dry_run=True` | **ENFORCED** |
| **Master Safety Lock** | `None` / `false` | `os.getenv("EXPERIMENT_EXECUTION_ENABLED")` | **LOCKED** |
| **Startup Reconciliation** | Clean (`action: none`) | `executor.reconcile_cluster_state()` | **PASS** |
| **Emergency Stop** | Functional | Unit tested via `executor.emergency_stop()` | **PASS** |

---

## 6. Data Preservation (TASK 4)

- **E01 Records Intact:** All artifacts in [`results/experiments/exp_20261110T152425_normal_traffic_838109a5/`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T152425_normal_traffic_838109a5/) were verified intact and unmodified.
- **Collision Resistance:** When authorized, E02 will be instantiated via `manager.create_experiment(WorkloadProfileName.GRADUAL_TRAFFIC_INCREASE)`, generating a unique directory:
  `results/experiments/exp_<timestamp>_gradual_traffic_increase_<uuid>/`
  No existing experiment records will be overwritten.

---

## 7. Automated Test Results (TASK 5)

All targeted and regression test suites were executed:

### Targeted E02 Concurrency & Workload Suite:
```bash
$ python -m pytest backend/tests/test_workload_and_experiments.py -v
======================= 37 passed, 4 warnings in 0.68s ========================
```
- `test_e02_concurrency_stage_tick_boundaries`: PASSED (Boundary values verified at $t=0, 30, 59.9, 60, 90, 119.9, 120, 150, 179.9, 180, 185\text{s}$).
- `test_e02_concurrency_spawn_rates_and_durations`: PASSED (Verified 2.0 u/s rate and ramp durations).
- `test_combined_locustfile_generation`: PASSED (Compiled combined locustfile code).
- `test_e02_watchdog_and_emergency_scale_zero`: PASSED (Verified scale-0 on expiry and emergency stop).

### Full Backend Regression Suite:
```bash
$ python -m pytest backend/tests/ -v
================= 166 passed, 2 skipped, 89 warnings in 6.79s =================
```
- **Actuator & Safety Tests:** 49 passed.
- **DPBPS Algorithm & Controller Tests:** 39 passed.
- **Kubernetes Telemetry & Prometheus Tests:** 39 passed.
- **Workload & Experiment Lifecycle Tests:** 37 passed.
- **Postgres / DB Tests:** 2 passed, 2 skipped.
- **Failures:** **0**.

---

## 8. Outstanding Risks and Research Observations

1. **High Ingress Amplification on `productcatalogservice`:**
   During E01 (10 users), `productcatalogservice` experienced 54.3 req/s ($5.4\times$ frontend load). Under 50 users (Stage 3), throughput may exceed 250 req/s.
   *Assessment:* This is the exact microservice bottleneck behavior DPBPS is designed to detect and prioritize. Actuator DRY-RUN posture guarantees cluster safety.
2. **Cartservice Memory Growth:**
   Cartservice memory consumed 64.4 MiB (100.7% of 64 MiB request) during E01. Under 50 users, heap allocation will grow.
   *Assessment:* Container hard limit is 128 MiB (50% headroom available). If utilization exceeds 80% of limit, DPBPS memory scoring will evaluate scaling needs in dry-run mode.

---

## 9. Final Readiness Verdict

### **FINAL VERDICT: GO (READY FOR OPERATOR AUTHORIZATION)**

All pre-execution requirements have been satisfied:
- Infrastructure, Prometheus, Grafana, and Metrics Server are fully operational.
- ConfigMap `dpbps-locust-e02` and Deployment volume mount are verified in Kubernetes.
- `loadgenerator` replicas is strictly **0**.
- Actuator is in **DRY-RUN** mode (`SCALING_ENABLED=false`).
- All 166 backend regression tests are passing.

```
+-----------------------------------------------------------------------------+
|                          PRE-EXECUTION GATE STATUS                          |
+-----------------------------------------------------------------------------+
| Task 1: Infrastructure Health                       | PASS (10/10 Ready)    |
| Task 2: ConfigMap & Locust Integration              | PASS (Mounted at 0 rep|
| Task 3: Safety Interlocks & Watchdog                | PASS (Strictly locked)|
| Task 4: E01 Data Preservation                       | PASS (Untouched)      |
| Task 5: Automated Testing                           | PASS (166 passed)     |
+-----------------------------------------------------------------------------+
| FINAL VERDICT                                       | GO                    |
+-----------------------------------------------------------------------------+
```

**Execution has halted. All systems are primed, verified, and awaiting operator authorization to initiate Experiment E02.**

