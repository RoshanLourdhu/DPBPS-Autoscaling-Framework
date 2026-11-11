# STAGE 8: DPBPS ALGORITHM VALIDATION UNDER CONTROLLED WORKLOADS
## Pre-Experiment Audit, Inconsistency Resolution, and Validation Plan

---

## 1. Executive Summary

This deliverable establishes the empirical validation framework for the research project:

> **"Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices"**
> Algorithm: **DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling**

Stage 8 aims to evaluate the core algorithmic behavior of DPBPS under controlled traffic conditions:
- Accurate detection and isolation of bottleneck microservices.
- Sensitivity to service call-graph dependencies.
- Differentiation between normal traffic and resource saturation.
- Bounded response to traffic surges ($\le 2$ replica delta per evaluation).
- Avoidance of premature or thrashing scale-down during lulls or active rollouts.
- Generation of safe, validated scaling recommendations without cluster disruption.

In strict compliance with Stage 8 safety mandates:
- **`SCALING_ENABLED=false`** is enforced.
- **The Kubernetes scaling actuator operates strictly in `DRY-RUN` mode.**
- **`loadgenerator` remains at `0` replicas.**
- **Zero workload experiments have been executed during this audit.**
- **Zero Kubernetes cluster mutations have occurred.**

---

## 2. Existing Environment Status

The audit confirmed the operational integrity of all system components:

| Component | Target / Environment | Operational Status | Telemetry Verified |
| :--- | :--- | :--- | :--- |
| **Kubernetes Engine** | Docker Desktop (`docker-desktop`) | Operational (v1.32.2) | Pod states & deployments queryable |
| **Online Boutique Namespace** | `online-boutique` | 12/12 Pods Ready (1/1 Running) | Zero unhandled restarts |
| **Monitoring Stack** | `monitoring` namespace | Prometheus (9090), Grafana (80) | Port-forwarded & responsive |
| **Metrics Server** | `kube-system` namespace | Operational (1/1 Ready) | CPU millicores & memory MiB streaming |
| **OpenTelemetry Collector** | `online-boutique` namespace | Port 4317 (gRPC), 8889 (Prometheus) | Ingesting RPC spans/metrics |
| **FastAPI Backend** | Python 3.13 / Uvicorn | 147 passed unit & regression tests | REST v1 router operational |
| **React Dashboard** | Vite 8.3.5 / React 19 | Production bundle compiled (0 errors) | Dry-run & profile panels ready |
| **Kubernetes Actuator** | `KubernetesScalingActuator` | **`DRY-RUN` Active** | Writes blocked; simulated logs active |
| **Load Generator** | `deployment/loadgenerator` | **`0/0` Replicas Active** | Headless Locust idle |

---

## 3. Stage 7 Implementation Audit

The code artifacts produced during Stage 7 were audited:

1. **Workload Module (`backend/workload/`)**:
   - `models.py`: Defines `WorkloadProfileName`, `WorkloadStage`, and `WorkloadProfileConfig`.
   - `profiles.py`: Canonical definitions for all 6 profiles.
   - `validation.py`: Safety envelopes ($users \le 200$, $spawn\_rate \le 50.0$, $duration \le 1200\text{s}$).
2. **Experiment Module (`backend/experiments/`)**:
   - `models.py`: Lifecycle states (`CREATED`, `READY`, `RUNNING`, `COMPLETED`, `STOPPED`, `FAILED`).
   - `manager.py`: File storage in `results/experiments/` with unique ID generation.
   - `metrics.py`: Data models preserving missing metrics as `None` (zero fabrication prevented).
3. **API Router (`backend/app/api/v1_router.py`)**:
   - Implemented endpoints for listing profiles, validating configurations, creating experiments, and querying metadata.
4. **Frontend Dashboard (`frontend/src/pages/ExperimentsPage.tsx`)**:
   - Interactive profile browser, multi-stage parameter inspector, and safety banners.

---

## 4. Workload Profile Inconsistencies & Resolutions

The Stage 7 audit identified six specific technical questions/inconsistencies. All have been investigated and formally resolved:

### Issue 1: Normal Traffic Duration Discrepancy
- **Audit Finding**: `backend/workload/profiles.py` defines `NORMAL_TRAFFIC` as: Ramp-Up ($5\text{s}$) + Steady Baseline ($120\text{s}$) + Ramp-Down ($5\text{s}$) = **$130\text{s}$ total**. However, the example execution instructions in `STAGE_7_FINAL_REPORT.md` stated $120\text{s}$.
- **Resolution**: The mathematically correct duration is **$130\text{ seconds}$**. The $5\text{s}$ ramp-up and $5\text{s}$ ramp-down are required to ensure Locust cleanly spawns the 10 users at $2\text{ users/s}$ ($10 / 2 = 5\text{s}$) and cleanly terminates them. The canonical configuration and execution instructions are unified at **$130\text{ seconds}$**.

### Issue 2: Gradual Traffic Increase Multi-Stage Execution
- **Audit Finding**: The profile requires 3 discrete stages: 10 users ($60\text{s}$), 25 users ($60\text{s}$), 50 users ($60\text{s}$). Total = $180\text{s}$.
- **Resolution**: Each $60\text{s}$ duration spans exactly 4 Prometheus scrape cycles ($15\text{s}$ scrape interval), providing sufficient sampling depth for the telemetry adapter to calculate rate derivatives and latency percentiles.

### Issue 3: Sudden Traffic Spike Transition Timing
- **Audit Finding**: The profile requires: Pre-Spike Baseline (5 users, $30\text{s}$), Sharp Spike Peak (80 users, $60\text{s}$), Post-Spike Recovery (5 users, $30\text{s}$). Total = $120\text{s}$.
- **Resolution**: Confirmed that the $30\text{s}$ pre-spike window establishes a clean quiescent baseline before injecting the 80-user surge at $20\text{ users/s}$. The bounded max delta constraint ($\le 2$ replicas) will be empirically evaluated during the surge.

### Issue 4: Bursty Traffic Dynamic User Transitions
- **Audit Finding**: The profile specifies 4 cycles of alternating bursts (60 users, $20\text{s}$) and recovery lulls (5 users, $20\text{s}$). Total = $160\text{s}$.
- **Investigation**: Does Locust support changing user concurrency dynamically without restarting?
- **Resolution**: **Yes**. In Locust, this is officially accomplished via the `LoadTestShape` class. Modifying environment variables via `kubectl set env` causes pod rolling updates, which interrupts connections and resets init containers. In contrast, a Locust `LoadTestShape` dynamically alters greenlet counts in-place every second via its `tick()` method. We created [`backend/workload/shape_generator.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/shape_generator.py) to translate any profile into standard Locust `LoadTestShape` Python code.

### Issue 5: Loadgenerator Deployment & Locust Environment Behavior
- **Audit Finding**:
  - In `microservices-demo/kubernetes-manifests/loadgenerator.yaml`, the container runs `locust --host="http://${FRONTEND_ADDR}" --headless -u "${USERS:-10}" -r "${RATE:-1}"`.
  - There is **no `--run-time` parameter**.
  - Therefore, if the deployment is scaled to 1 replica, Locust runs indefinitely until explicitly scaled back to 0!
- **Resolution**:
  - The experiment management framework must enforce an automated termination timeout.
  - An automated supervisor or script must issue `kubectl scale deployment/loadgenerator -n online-boutique --replicas=0` precisely when the experiment duration elapses, backed by a watchdog timeout ($duration + 10\text{s}$).

### Issue 6: Experiment Execution Safety Interlock Design
- **Audit Finding**: Stage 7 threw `RuntimeError` and HTTP 403 on transitions to `RUNNING` to prevent premature traffic generation.
- **Resolution**: We designed [`backend/experiments/executor.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/experiments/executor.py) with a controlled two-key interlock:
  1. `EXPERIMENT_EXECUTION_ENABLED`: System environment variable (defaults to `False`).
  2. Explicit operator approval token required in the execution payload.
  3. Pre-flight checks verify `SCALING_ENABLED=False` and all 10 pods ready.
  4. Automatic watchdog timer terminates traffic if the time limit is reached.
  5. Immediate emergency stop endpoint `POST /api/v1/experiments/{id}/stop` forces `replicas=0`.

---

## 5. Summary Table: Six Workload Profiles Status

| Profile Name | Target Concurrency | Spawn Rate | Total Duration | Stages Count | Dynamic Shape | Safety Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`NORMAL_TRAFFIC`** | 10 users | 2.0 /s | 130s | 3 stages | Linear Ramp/Hold | **Validated & Ready (Baseline)** |
| **`GRADUAL_TRAFFIC_INCREASE`** | 10 $\rightarrow$ 25 $\rightarrow$ 50 | 2.0 /s | 180s | 3 stages | Stepped Staircase | **Validated & Ready** |
| **`SUDDEN_TRAFFIC_SPIKE`** | 5 $\rightarrow$ 80 $\rightarrow$ 5 | 20.0 /s | 120s | 3 stages | Pulse Surge | **Validated & Ready** |
| **`SUSTAINED_HIGH_TRAFFIC`** | 60 users | 5.0 /s | 220s | 3 stages | Plateau Saturation | **Validated & Ready** |
| **`TRAFFIC_DECREASE`** | 50 $\rightarrow$ 25 $\rightarrow$ 5 | 5.0 /s | 180s | 3 stages | Descending Step | **Validated & Ready** |
| **`BURSTY_TRAFFIC`** | 60 $\leftrightarrow$ 5 (4x) | 20.0 /s | 160s | 8 stages | Square-Wave Burst | **Validated & Ready** |

---

## 6. Baseline Telemetry Audit Results (Live Cluster)

Prior to executing any workload, live baseline telemetry was audited via `KubernetesTelemetryAdapter` and Prometheus:

```
================================================================================
STAGE 8 BASELINE TELEMETRY AUDIT (IDLE CLUSTER)
================================================================================
Total Deployments Found: 13
Valid Instrumented Microservices: 10
Excluded Uninstrumented Components: 3 (loadgenerator, opentelemetrycollector, redis-cart)
--------------------------------------------------------------------------------
INSTRUMENTED MICROSERVICES TELEMETRY:
  - adservice              | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  0.94% | Mem: 60.82% | Reps: 1 | Deps: []
  - cartservice            | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  1.52% | Mem: 100.0% | Reps: 1 | Deps: ['redis-cart']
  - checkoutservice        | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  0.97% | Mem: 13.31% | Reps: 1 | Deps: [6 services]
  - currencyservice        | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  1.42% | Mem: 63.85% | Reps: 1 | Deps: []
  - emailservice           | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  6.20% | Mem: 72.71% | Reps: 1 | Deps: []
  - frontend               | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  1.31% | Mem: 19.45% | Reps: 1 | Deps: [7 services]
  - paymentservice         | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  2.18% | Mem: 62.46% | Reps: 1 | Deps: []
  - productcatalogservice  | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  1.00% | Mem: 13.64% | Reps: 1 | Deps: []
  - recommendationservice  | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  5.15% | Mem: 14.90% | Reps: 1 | Deps: ['productcatalogservice']
  - shippingservice        | RPS:   0.0 | P95:    0.0ms | Err:  0.00 | CPU:  1.23% | Mem: 13.69% | Reps: 1 | Deps: []
--------------------------------------------------------------------------------
EXCLUDED COMPONENTS (SAFE NON-FABRICATED TELEMETRY):
  - loadgenerator          | Missing: ['desired_replicas_is_zero'] | Status: 0 replicas (Idle)
  - opentelemetrycollector | Missing: ['error_rate', 'p95_latency', 'request_rate'] | Diagnostics: Preserved as None
  - redis-cart             | Missing: ['error_rate', 'p95_latency', 'request_rate'] | Diagnostics: Preserved as None
--------------------------------------------------------------------------------
DPBPS CONTROLLER BASELINE DECISIONS:
Detected Bottleneck: None
All 10 Microservices: Action = HOLD (Previous: 1 -> Proposed: 1)
Reason: "Pressure within bounds – hold"
================================================================================
```

---

## 7. Experiment Measurement and Evaluation Methodology

To evaluate DPBPS during controlled load testing, the following metric dimensions will be captured:

### A. Telemetry Dimensions
1. **Workload Metrics**: Active Locust users, achieved RPS, total requests, failed requests, failure rate.
2. **Application Performance**: Per-service RPS, P50 latency (ms), P95 latency (ms), P99 latency (ms), error fraction.
3. **Infrastructure Metrics**: CPU millicores and utilization %, memory MiB and utilization %, desired and ready replicas.
4. **Algorithmic Metrics**: Detected bottleneck service, bottleneck priority score, downstream impact factor, deployment phase, DPBPS action (`SCALE_UP`, `SCALE_DOWN`, `HOLD`), proposed replica count, actuator dry-run status, and decision rationale.

### B. Formal Evaluation Criteria
- **Bottleneck Detection Accuracy**: Evaluated by verifying whether the algorithm identifies the known saturated dependency (e.g. `cartservice` under checkout load) vs. upstream callers (`frontend`).
- **Decision Response Latency**: Time elapsed from traffic injection inflection to the first `SCALE_UP` recommendation.
- **Scaling Stability / Thrashing Rate**: Number of directional scaling reversals (Scale-Up followed immediately by Scale-Down within cooldown window).
- **Replica Recommendation Overhead**: Normalized difference between peak recommended replicas and minimum required replicas to satisfy latency target ($200\text{ms}$).
- **Recovery Time**: Time required for decisions to return to `HOLD` after traffic cessation.

---

## 8. Data Storage Architecture

Every future experiment run will write structured artifacts to `results/experiments/<experiment_id>/`:

```
results/experiments/<experiment_id>/
├── experiment_config.json      # Full workload parameters and stage definitions
├── workload_metrics.json       # Locust user count, achieved RPS, failure statistics
├── telemetry_metrics.json      # Time-series of Prometheus & K8s Metrics Server snapshots
├── dpbps_decisions.json        # Time-series of DPBPS controller decisions per service
├── actuator_audit.json         # Time-series of simulated actuator dry-run checks
├── experiment_summary.json     # Summary KPIs (peak RPS, P95, bottleneck, duration)
└── experiment.log              # Detailed execution event log with UTC timestamps
```

---

## 9. Code Modifications Summary

1. **[`backend/workload/shape_generator.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/shape_generator.py)** *(Created)*:
   - Implements `generate_locust_shape_stages` and `generate_locust_shape_code` translating profile configurations into dynamic Locust `LoadTestShape` classes.
2. **[`backend/experiments/executor.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/experiments/executor.py)** *(Created)*:
   - Implements `ExperimentExecutor` with the master safety lock, pre-flight safety validator, directory initializer (creating all 7 structured output files), and `emergency_stop` mechanism.
3. **[`backend/app/api/v1_router.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/app/api/v1_router.py)** *(Updated)*:
   - Added `GET /api/v1/experiments/{id}/safety-check` returning safety gate evaluations.
   - Added `POST /api/v1/experiments/{id}/stop` providing instant emergency stop functionality.
4. **[`frontend/src/services/api.ts`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/frontend/src/services/api.ts)** *(Updated)*:
   - Added `checkExperimentSafety()` and `stopExperiment()` API helper functions.
5. **[`frontend/src/pages/ExperimentsPage.tsx`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/frontend/src/pages/ExperimentsPage.tsx)** *(Updated)*:
   - Wired emergency stop buttons into the experiment registry table.
   - Updated safety banners and tooltips to explicitly reflect Stage 8 validation requirements.
6. **[`backend/tests/test_workload_and_experiments.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/tests/test_workload_and_experiments.py)** *(Updated)*:
   - Added 6 new unit tests for shape generation, executor safety lock, directory initialization, and emergency stop endpoints (total: 27 tests).

---

## 10. Test and Regression Results

- **Workload & Experiments Test Suite**:
  ```powershell
  python -m pytest backend/tests/test_workload_and_experiments.py -v
  ```
  **Outcome:** **27 passed, 0 failed** in 0.89s.

- **Full Backend Regression Suite**:
  ```powershell
  python -m pytest backend/tests -q
  ```
  **Outcome:** **147 passed, 2 skipped, 0 failures** in 2.73s.
  *(Progression: Baseline 110 $\rightarrow$ Stage 6: 120 $\rightarrow$ Stage 7: 141 $\rightarrow$ Stage 8 Audit: 147).*

- **Frontend Production Build**:
  ```powershell
  cd frontend && npm run build
  ```
  **Outcome:** `built in 2.04s` — **0 TypeScript errors, 0 lint warnings**.

---

## 11. Remaining Limitations

1. **Finite Docker Desktop Resources**: Local development machine has shared CPU/memory. Peak safe concurrency across all tests must remain capped at $\le 200$ users.
2. **Prometheus Scrape Interval ($15\text{s}$)**: Metric changes require approximately $15\text{--}30\text{ seconds}$ to propagate from application export through OpenTelemetry Collector to Prometheus time-series storage.

---

## 12. Recommended Next Action: Experiment E01 (NORMAL_TRAFFIC Baseline)

Once explicit operator approval is granted, the first recommended experiment to execute is:

### Experiment E01: `NORMAL_TRAFFIC` Baseline Validation
- **Objective**: Establish baseline application behavior and empirically verify that DPBPS produces `HOLD` decisions without false scale-up alarms under steady, light traffic.
- **Parameters**: 10 users, spawn rate 2.0 users/s, total duration 130s.
- **Target Application**: `http://frontend:80`

---

## 13. Required Review Information

As specified in the Stage 8 mandatory stop instructions:

1. **What was inspected**:
   - DPBPS controller, bottleneck detector, deployment state manager, and telemetry adapter.
   - Stage 7 workload profiles, experiment manager, and API router.
   - Online Boutique `loadgenerator.yaml`, Dockerfile entrypoint, and `locustfile.py`.
   - Live Prometheus metrics, Metrics Server, and all 12 pods in `online-boutique`.
2. **What was modified**:
   - Created `backend/workload/shape_generator.py` for dynamic multi-stage Locust execution.
   - Created `backend/experiments/executor.py` for controlled execution supervision and emergency stopping.
   - Extended `backend/app/api/v1_router.py` with `/safety-check` and `/stop` endpoints.
   - Updated `frontend/src/services/api.ts` and `frontend/src/pages/ExperimentsPage.tsx`.
   - Extended `backend/tests/test_workload_and_experiments.py` (27 tests).
3. **What issues were discovered**:
   - $120\text{s}$ vs $130\text{s}$ duration discrepancy in documentation.
   - Headless Locust lacks a `--run-time` flag in the existing container entrypoint, requiring external supervisor shutdown.
   - Modifying environment variables on Kubernetes triggers pod rolling updates rather than dynamic in-process user scaling.
4. **What issues were resolved**:
   - Standardized `NORMAL_TRAFFIC` duration at $130\text{s}$ ($5\text{s} + 120\text{s} + 5\text{s}$).
   - Prepared `LoadTestShape` generator for seamless dynamic in-process concurrency transitions.
   - Implemented `ExperimentExecutor` with watchdog timeout and emergency stop.
5. **Test results**:
   - **147 passed, 2 skipped, 0 failures** in full backend regression.
   - Frontend build passed in 2.04s.
6. **Whether the system is ready for E01 (NORMAL_TRAFFIC Baseline)**:
   - **YES**. All 10 microservices are healthy, Prometheus is reachable, the controller evaluates idle telemetry to `HOLD`, and the safety framework is validated.
7. **The exact command that would initiate E01**:
   ```bash
   # COMMAND FOR FUTURE APPROVED EXECUTION OF E01 (DO NOT RUN WITHOUT APPROVAL):
   kubectl set env deployment/loadgenerator -n online-boutique USERS=10 RATE=2 FRONTEND_ADDR=frontend:80
   kubectl scale deployment/loadgenerator -n online-boutique --replicas=1
   # After 130 seconds:
   kubectl scale deployment/loadgenerator -n online-boutique --replicas=0
   ```
8. **Expected resource impact and emergency-stop procedure**:
   - **Resource Impact**: ~10-15 aggregate RPS, < 0.2 CPU cores, < 50MiB additional memory. Negligible risk to cluster stability.
   - **Emergency Stop Procedure**:
     - Immediate CLI command: `kubectl scale deployment/loadgenerator -n online-boutique --replicas=0`
     - Or API trigger: `POST /api/v1/experiments/{experiment_id}/stop`
     - Or UI button: Click "Stop" in the Experiments Registry table.

---

## FINAL STOP CONDITION MET

All Phase A through Phase H audit and preparation tasks are complete.
- **No workload experiments have been launched.**
- **`loadgenerator` remains at `0` replicas.**
- **`SCALING_ENABLED=false` remains enforced.**
- **Actuator remains in `DRY-RUN` mode.**

Awaiting your explicit approval before executing Experiment E01 (NORMAL_TRAFFIC Baseline).

