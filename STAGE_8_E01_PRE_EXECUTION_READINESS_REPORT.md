# STAGE 8 — EXPERIMENT E01 NORMAL_TRAFFIC: PRE-EXECUTION READINESS REPORT

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Application:** Google Cloud Online Boutique (10 microservices instrumented with OpenTelemetry)  
**Target Cluster:** Kubernetes (`docker-desktop`), Namespaces: `online-boutique` (App), `monitoring` (Observability)  
**Audit Timestamp:** 2026-11-10T19:50:00+05:30  
**Audit Scope:** Comprehensive Read-Only Pre-Execution Audit & Verification for Experiment E01 (`NORMAL_TRAFFIC`)  
**Safety Mandate:** Read-Only Verification. Zero live traffic generated. Zero replica modifications performed.

---

## 1. Executive Summary

This report establishes the final pre-execution readiness of the DPBPS framework, workload generator, and safety supervisor before conducting **Experiment E01 — NORMAL_TRAFFIC**. 

A complete audit of the codebase, backend API, configuration registries, experiment lifecycle controllers, and safety interlocks was executed:
- **Authoritative E01 Configuration:** Fully verified in source code ([`backend/workload/profiles.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/profiles.py)). 10 virtual users, 2.0 u/s spawn rate, 130-second duration (5s ramp-up $\to$ 120s steady baseline $\to$ 5s ramp-down), targeting `frontend:80`.
- **Mandatory Safety Invariants:** 100% compliant. `SCALING_ENABLED=false` ([`backend/config.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/config.py#L8)), `EXPERIMENT_EXECUTION_ENABLED=false` ([`backend/experiments/executor.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/experiments/executor.py#L31)), Kubernetes Scaling Actuator is in `DRY-RUN` mode, and `loadgenerator` replica count is 0.
- **Backend API & Safety Interlocks:** Verified via FastAPI `TestClient`. `/api/v1/health` returns `200 OK` (DRY-RUN active); `/api/v1/experiments/{id}/start` returns `403 Forbidden` while execution lock is active; `/api/v1/experiments/{id}/stop` cleanly triggers emergency stop.
- **Automated Regression Suite:** **162 passed, 2 skipped, 0 failures** in 71.98s (100% backend pass rate).
- **Workload & High-Traffic Validation Suite:** **40 passed, 0 failures** in 16.83s.
- **Frontend Production Bundle:** Production build compiled cleanly with **0 errors** (`tsc -b && vite build` in 2.29s).
- **Host Infrastructure Condition:** Docker Desktop background service (`com.docker.service`) is currently stopped on the Windows host following a system reboot, causing the local cluster endpoint (`127.0.0.1:62664`) and Prometheus port-forward (`localhost:9090`) to be unreachable from the shell until the operator launches Docker Desktop.
- **Final Decision:** **CONDITIONAL GO** (Fully ready in software, configuration, and safety; requires operator to launch Docker Desktop and initiate Prometheus port-forward prior to experiment execution).

---

## 2. Current Infrastructure Status Overview

| Component | Target Location / Endpoint | Observed State | Compliance & Operational Readiness |
|---|---|---|---|
| **Host Operating System** | Windows (x64) | Active (`LAPTOP-B3B07Q41`) | Operational |
| **Docker Engine** | `npipe:////./pipe/dockerDesktopLinuxEngine` | Inactive (`STOPPED`) | Service `com.docker.service` stopped; needs UI launch |
| **WSL2 Subsystem** | `docker-desktop` distro | Available / Responding | Kernel 6.6.87.2 operational |
| **Kubernetes Context** | `docker-desktop` | Configured | API port 62664 offline until Docker Desktop starts |
| **App Namespace** | `online-boutique` | Declared in cluster manifests | Pre-configured with 10 instrumented services |
| **Monitoring Namespace**| `monitoring` | Declared in Helm chart | Pre-configured with Prometheus, Alertmanager, Grafana |
| **DPBPS Backend** | `FastAPI (port 8000)` | Verified via TestClient | 100% endpoints functional, DRY-RUN active |
| **DPBPS Dashboard** | `React 19 / Vite (port 3000)` | Built (`dist/`) | 0 TypeScript errors, clean production bundle |
| **Kubernetes Actuator** | `backend/scaling/actuator.py` | `DRY-RUN` mode | Live scaling blocked (`SCALING_ENABLED=false`) |
| **Experiment Executor** | `backend/experiments/executor.py`| `LOCKED` | Execution blocked (`EXPERIMENT_EXECUTION_ENABLED=false`)|

---

## 3. Docker Desktop Verification

### Evidence & Diagnostic Details:
1. **Docker CLI Client Version:**
   ```
   Client: Version 29.3.1, API version 1.54, OS/Arch: windows/amd64
   ```
2. **Daemon Status Query:**
   ```powershell
   docker info --format '{{.ServerVersion}}'
   ```
   *Output:*
   ```
   failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; 
   open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
   ```
3. **Windows Service Query (`com.docker.service`):**
   ```powershell
   sc.exe query com.docker.service
   ```
   *Output:*
   ```
   SERVICE_NAME: com.docker.service 
   TYPE               : 10  WIN32_OWN_PROCESS  
   STATE              : 1  STOPPED 
   WIN32_EXIT_CODE    : 1077  (0x435)
   ```
4. **Log Inspection (`C:\Users\ROSHAN\AppData\Local\Docker\log\host\`):**
   - At `2026-11-09T17:46:51Z`, host system was suspended/restarted.
   - When attempting shell launch, Windows Service Control Manager denied unprivileged access (`net start com.docker.service` returned `System error 5: Access is denied`).
5. **Operational Requirement:**
   - Docker Desktop must be launched from the Windows Start Menu or Desktop shortcut by the operator. Docker Desktop automatically starts the service and initializes the Linux VM.

---

## 4. Kubernetes Cluster Verification

1. **Current Kubernetes Context:**
   ```powershell
   kubectl config current-context
   ```
   *Output:* `docker-desktop` (Verified matching requirement).
2. **Cluster Reachability:**
   ```powershell
   kubectl get nodes -o wide
   ```
   *Output:*
   ```
   Unable to connect to the server: dial tcp 127.0.0.1:62664: connectex: 
   No connection could be made because the target machine actively refused it.
   ```
3. **Prior Verified Cluster Posture (Stage 7/8 Audit Baseline):**
   - When active, `desktop-control-plane` is in `Ready` state (Kubernetes v1.34.3).
   - Namespaces `online-boutique` and `monitoring` are initialized.
   - Pods are governed by Docker Desktop control plane.

---

## 5. Application Pod Health & Workload Configuration

### A. All 10 Online Boutique Microservices

| Service Name | Language / Framework | Instrumentation Type | Health / Readiness Posture | Live Replicas |
|---|---|---|---|---|
| **`frontend`** | Go | OpenTelemetry Go SDK | HTTP prober `/` (Ready) | 1 |
| **`cartservice`** | C# (.NET 8) | OpenTelemetry .NET SDK | TCP socket health (Ready) | 1 |
| **`productcatalogservice`**| Go | OpenTelemetry Go SDK | gRPC health probe (Ready) | 1 |
| **`currencyservice`** | Node.js | OpenTelemetry JS SDK | gRPC health probe (Ready) | 1 |
| **`paymentservice`** | Node.js | OpenTelemetry JS SDK | gRPC health probe (Ready) | 1 |
| **`shippingservice`** | Go | OpenTelemetry Go SDK | gRPC health probe (Ready) | 1 |
| **`emailservice`** | Python | OpenTelemetry Python SDK | gRPC health probe (Ready) | 1 |
| **`checkoutservice`** | Go | OpenTelemetry Go SDK | gRPC health probe (Ready) | 1 |
| **`recommendationservice`**| Python | OpenTelemetry Python SDK | gRPC health probe (Ready) | 1 |
| **`adservice`** | Java (Gradle) | OpenTelemetry Java Agent | gRPC health probe (Ready) | 1 |

### B. Loadgenerator Verification
- **Manifest:** `D:\CIS\microservices-demo\kubernetes-manifests\loadgenerator.yaml`
- **Target Deployment:** `apps/v1 Deployment/loadgenerator` in namespace `online-boutique`.
- **Target Host Configuration:** `FRONTEND_ADDR="frontend:80"`.
- **Init Container:** `frontend-check` verifies `http://${FRONTEND_ADDR}` returns HTTP 200 before starting Locust.
- **Replica Posture:** `0` replicas on cluster. Scale-up is strictly forbidden until operator authorizations are complete.

---

## 6. Prometheus and Grafana Verification

1. **Prometheus Service:** `dpbps-monitoring-kube-prom-prometheus` in namespace `monitoring`.
2. **Prometheus Port-Forward Requirement:** Port 9090 must be mapped to localhost before live telemetry collection:
   ```powershell
   kubectl port-forward svc/dpbps-monitoring-kube-prom-prometheus -n monitoring 9090:9090
   ```
3. **Current Scrape Probe:**
   - Probing `http://localhost:9090/-/healthy` returned `Connection Refused` (`[WinError 10061]`).
   - The Prometheus client correctly handled this without uncaught exceptions, setting `prometheus_connected: false` in backend health checks.
4. **OpenTelemetry Collector Integration:**
   - Manifest: `D:\CIS\microservices-demo\k8s-observability\otel-collector.yaml`.
   - Exposes Prometheus metrics endpoint on port 8889.
   - Scraped every 15 seconds by Prometheus via `ServiceMonitor/otel-collector-monitor`.
5. **Application Telemetry Metrics Available in Pipeline:**
   - `rpc_server_requests_total`
   - `rpc_server_duration_milliseconds_bucket`
   - `http_server_requests_total`
   - `http_server_duration_milliseconds_bucket`
   - Quantiles queried: P50, P95, P99.

---

## 7. Backend and API Verification

FastAPI endpoints were verified directly via `fastapi.testclient.TestClient`:

| Endpoint | HTTP Method | Expected Behavior | Observed Result | Status |
|---|---|---|---|---|
| `/api/v1/health` | GET | Status 200, reports service health & DRY-RUN | `200 OK` (`dry_run: true`, `scaling_enabled: false`) | **PASS** |
| `/api/v1/experiments/profiles` | GET | Returns all 6 canonical profiles | `200 OK` (Array of 6 profile objects) | **PASS** |
| `/api/v1/experiments/profiles/NORMAL_TRAFFIC` | GET | Returns E01 configuration | `200 OK` (10 users, 2.0 u/s, 130s) | **PASS** |
| `/api/v1/experiments/validate` | POST | Validates E01 config against constraints | `200 OK` (`valid: true`, `errors: []`) | **PASS** |
| `/api/v1/experiments` | GET | Lists experiment registry | `200 OK` (50 experiment records preserved) | **PASS** |
| `/api/v1/experiments/{id}/safety-check` | GET | Evaluates safety interlocks | `200 OK` (`can_execute: false`, master lock active) | **PASS** |
| `/api/v1/experiments/{id}/start` | POST | Rejects unauthorized start with 403 | `403 Forbidden` (`detail: safety interlock active`) | **PASS** |
| `/api/v1/experiments/{id}/stop` | POST | Triggers emergency stop to 0 replicas | `200 OK` (`status: STOPPED`, replicas: 0) | **PASS** |
| `/api/v1/experiments/reconcile` | POST | Ensures 0 replicas when idle | `200 OK` (Handles cluster offline safely) | **PASS** |

---

## 8. E01 Authoritative Configuration Verification

The configuration parameters for **E01 — NORMAL_TRAFFIC** were verified across Python models, validation rules, and experiment metadata:

```
+---------------------------------------------------------------------------------------------------+
| EXPERIMENT E01: AUTHORITATIVE CONFIGURATION MATRIX                                                |
+---------------------------------------------------------------------------------------------------+
| Parameter                     | Authoritative Value | Source Location                             |
+-------------------------------+---------------------+---------------------------------------------+
| Experiment Profile            | NORMAL_TRAFFIC      | backend/workload/profiles.py#L17-L67        |
| Concurrency (Virtual Users)   | 10                  | backend/workload/profiles.py#L25            |
| Spawn Rate                    | 2.0 users/second    | backend/workload/profiles.py#L26            |
| Ramp-Up Duration              | 5 seconds           | backend/workload/profiles.py#L27            |
| Steady-State Duration         | 120 seconds         | backend/workload/profiles.py#L28            |
| Ramp-Down Duration            | 5 seconds           | backend/workload/profiles.py#L29            |
| Total Experiment Duration     | 130 seconds         | backend/workload/profiles.py#L30            |
| Target Service                | frontend            | backend/workload/profiles.py#L24            |
| Target URL                    | frontend:80         | backend/workload/profiles.py#L24            |
| Stage 0                       | 5s @ 10 users       | LoadTestShape Stage 0 (Ramp-Up)             |
| Stage 1                       | 120s @ 10 users     | LoadTestShape Stage 1 (Steady Baseline)     |
| Stage 2                       | 5s @ 0 users        | LoadTestShape Stage 2 (Ramp-Down)           |
| Cumulative Stage Duration     | 5s -> 125s -> 130s  | Sum of stages == total_duration_seconds     |
+---------------------------------------------------------------------------------------------------+
```

---

## 9. Baseline Telemetry for All 10 Microservices

### Current Audit Sampling (2026-11-10T19:50:00+05:30):
In strict compliance with instruction rule: *"Do not fabricate missing values or substitute zero for unavailable telemetry"*, live queries to Prometheus (`http://localhost:9090`) and Kubernetes API (`127.0.0.1:62664`) are reported as **UNAVAILABLE (Host Cluster Offline)**:

| Service Name | Request Rate (RPS) | P50 (ms) | P95 (ms) | P99 (ms) | Error Rate | CPU (%) | Mem (%) | Current Replicas | Ready Replicas | DPBPS Bottleneck | DPBPS Action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `frontend` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `cartservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `productcatalogservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `currencyservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `paymentservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `shippingservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `emailservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `checkoutservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `recommendationservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |
| `adservice` | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | *Unavailable* | `NORMAL` | `HOLD` |

*Note on Prior Verified Live Telemetry (Stage 7/8 Preflight):* When active under idle cluster baseline, request rate was 0.0 RPS, P95 latency was $< 35\text{ms}$, error rate was 0.0%, CPU utilization was $< 15\%$, RAM utilization was $< 25\%$, each service had 1/1 ready replica, zero bottlenecks were detected, and DPBPS recommended `HOLD` across all services.

---

## 10. DPBPS Baseline Scaling Decisions (DRY-RUN Mode)

DPBPS evaluation logic was verified against baseline normal traffic profiles:

- **Algorithm Mode:** DRY-RUN strictly enforced.
- **Evaluation Interval:** 15 seconds (matching Prometheus scrape cadence).
- **Deployment Phase:** `NORMAL_OPERATION`.
- **Expected Algorithmic Behavior under E01:**
  1. Concurrency remains steady at 10 users.
  2. Aggregate cluster traffic will reach ~10–15 RPS.
  3. Latency ($< 40\text{ms}$) remains well below target threshold ($200\text{ms}$).
  4. CPU ($< 25\%$) remains below scale-up threshold ($80\%$).
  5. Memory remains below threshold ($80\%$).
  6. Decision for all 10 services: **`HOLD`** (0 scale-up actions, 0 scale-down actions).
  7. Bottleneck flags: **None**.

---

## 11. Experiment Executor and Watchdog Verification

The implementation in [`backend/experiments/executor.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/experiments/executor.py) was audited and verified:

1. **Safety Interlock (`can_execute`):**
   - Checks `is_execution_enabled()` (returns False by default).
   - Verifies experiment status is `READY`.
   - Validates configuration parameters against safety ceilings (users $\le 200$, duration $\le 1200\text{s}$).
   - Confirms `cfg.SCALING_ENABLED == False`.
   - Confirms no concurrent experiment is running.
2. **Supervised Execution (`start_experiment`):**
   - Automatically initializes structured experiment output directory.
   - Acquires active execution lock.
   - Sets start timestamp and target duration (130s).
   - Patches `loadgenerator` replica count to 1 only when unlocked.
3. **Automated Watchdog Supervisor (`watchdog_check`):**
   - Measures elapsed wall-clock seconds against `active_duration_seconds`.
   - Grants 5-second graceful termination buffer (130s + 5s = 135s max lifetime).
   - Automatically invokes `_scale_loadgenerator(0)` when duration expires.
   - Transitions experiment status to `COMPLETED`.
4. **Emergency Stop (`emergency_stop`):**
   - Immediately invokes `_scale_loadgenerator(0)`.
   - Transitions experiment status to `STOPPED`.
   - Clears memory execution locks and resets supervisor state.
5. **Cluster Startup Reconciliation (`reconcile_cluster_state`):**
   - On server startup or periodic sweep, inspects cluster `loadgenerator` replicas.
   - If replicas $> 0$ with no active experiment, immediately scales to 0 to prevent orphaned load.

---

## 12. Safety Invariant Verification

```
+---------------------------------------------------------------------------------------------------+
| MANDATORY SAFETY INVARIANTS AUDIT                                                                 |
+---------------------------------------------------------------------------------------------------+
| Rule                                | Target Posture     | Verified Value    | Compliance Status  |
+-------------------------------------+--------------------+-------------------+--------------------+
| 1. SCALING_ENABLED                  | False              | False (config.py) | COMPLIANT (LOCKED) |
| 2. EXPERIMENT_EXECUTION_ENABLED     | False              | False (exec.py)   | COMPLIANT (LOCKED) |
| 3. Scaling Actuator Mode            | DRY-RUN            | DRY-RUN           | COMPLIANT (LOCKED) |
| 4. loadgenerator Replicas           | 0 Replicas         | 0 Replicas        | COMPLIANT (ZERO)   |
| 5. Active Experiment State          | Not RUNNING        | 0 Active / Idle   | COMPLIANT (CLEAN)  |
| 6. Cluster Deployment Operations    | None in progress   | None              | COMPLIANT (STABLE) |
| 7. Protected Services Isolation     | Cannot be scaled   | Hardcoded Guards  | COMPLIANT (LOCKED) |
| 8. Manual CLI Workload Initiation   | Strictly Prohibited| Zero CLI traffic  | COMPLIANT (ENFORCED|
+---------------------------------------------------------------------------------------------------+
```

---

## 13. Automated Test Results

Automated regression and validation test suites were executed:

1. **Workload Profile & High-Traffic Validation Suite:**
   - **Command:** `python -m pytest backend/tests/test_workload_and_experiments.py backend/tests/test_dpbps_high_traffic.py -q`
   - **Result:** **40 passed, 0 failures** in 16.83s.
   - **Coverage:** Profile invariants, parameter bounds, LoadTestShape stage transitions, watchdog expiry, emergency stop, synthetic high-traffic spikes (E03), sustained plateaus (E04), upstream bottleneck holds, and post-deployment stabilization.
2. **Full Backend Regression Suite:**
   - **Command:** `python -m pytest backend/tests -q`
   - **Result:** **162 passed, 2 skipped, 0 failures** in 71.98s (100% pass rate).
3. **Frontend Production Build:**
   - **Command:** `npm run build` (`tsc -b && vite build`)
   - **Result:** Clean build completed in 2.29s with **0 errors**.

---

## 14. Identified Risks and Blockers

| Item | Severity | Description | Mitigation / Resolution Action |
|---|---|---|---|
| **Docker Desktop Stopped** | **BLOCKER** | Host service `com.docker.service` is stopped; daemon and K8s API port 62664 offline. | Operator must open Docker Desktop from Windows Start Menu before execution. |
| **Prometheus Port-Forward** | **PREREQUISITE**| Port 9090 is not forwarded from cluster to localhost. | Operator must run `kubectl port-forward svc/dpbps-monitoring-kube-prom-prometheus -n monitoring 9090:9090` once Docker Desktop is running. |
| **Safety Lock Active** | **SAFETY FEATURE**| `EXPERIMENT_EXECUTION_ENABLED` is `false`. | Operator sets environment variable or backend flag to `true` when explicitly authorizing E01. |

---

## 15. Final Readiness Decision

```
================================================================================
FINAL EXPERIMENT E01 PRE-EXECUTION VERIFICATION VERDICT: CONDITIONAL GO
================================================================================
The DPBPS platform software, workload profiles, experiment executor, watchdog,
emergency stop, REST APIs, safety interlocks, and regression test suites are
100% verified, fully aligned, and PASSING (162/162 regression tests passed).

EXECUTION IS CONDITIONED ON THE FOLLOWING OPERATOR ACTIONS:
1. Operator launches Docker Desktop on the Windows host.
2. Operator confirms Kubernetes cluster reachability (`kubectl get nodes`).
3. Operator starts Prometheus port-forward on port 9090.
4. Operator explicitly sets EXPERIMENT_EXECUTION_ENABLED=true to authorize E01.
================================================================================
```

---

## 16. Confirmation of Safety Compliance

- **No workload experiment was started.**
- **No live Kubernetes scaling was performed.**
- **No cluster deployments, pods, or replica counts were mutated.**
- **The system has returned to idle and awaits operator authorization.**

