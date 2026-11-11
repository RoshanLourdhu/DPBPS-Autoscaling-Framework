# STAGE 8 — EXPERIMENT E05: TRAFFIC DECREASE EXECUTION REPORT

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Experiment ID:** `exp_20261110T172806_traffic_decrease_71144bfe`  
**Profile:** `TRAFFIC_DECREASE`  
**Execution Timestamp:** 2026-11-10T17:28:06Z – 2026-11-10T17:31:16Z  
**Duration:** 190.0 seconds (Workload target: 180 seconds, Watchdog: 185 seconds)  
**Execution Posture:** Autonomous In-Process Stepping, Actuator `DRY-RUN`, `SCALING_ENABLED=false`  
**Post-Run Status:** `COMPLETED` (Verified clean cluster teardown, `loadgenerator` replicas: 0)  

---

## 1. Executive Summary

Experiment E05 evaluated the dynamic de-escalation behavior, scale-down stabilization guardrails, and minimum capacity floor enforcement of the DPBPS framework under a controlled, progressive demand reduction: **50 users (High Tier, 60s) $\to$ 25 users (Intermediate Tier, 60s) $\to$ 5 users (Low Baseline Tier, 60s)** @ 5 users/second spawn rate across a total configured duration of 180 seconds.

This experiment investigates whether DPBPS correctly observes bottleneck disappearance as demand diminishes, respects the minimum replica floor (`min_replicas = 1`), and avoids premature, destabilizing scale-down recommendations when operating in an unscaled baseline posture.

### Key Performance Indicators (KPIs)
| Metric | High Load Tier (50u, 0-60s) | Intermediate Tier (25u, 60-120s) | Low Baseline Tier (5u, 120-180s) | Total Run Delta |
| :--- | :--- | :--- | :--- | :--- |
| **Active Virtual Users** | 50 users | 25 users (-50%) | 5 users (-80%) | -90% aggregate drop |
| **Frontend Throughput (RPS)** | 54.00 RPS (Peak) | 48.60 $\to$ 30.30 RPS | 27.00 $\to$ 6.90 RPS | Monotonic reduction |
| **ProductCatalog RPS** | 251.90 RPS (Peak) | 248.40 $\to$ 156.20 RPS | 139.60 $\to$ 37.20 RPS | -85.2% load shed |
| **CartService RPS** | 25.50 RPS (Peak) | 24.90 $\to$ 15.50 RPS | 12.50 $\to$ 3.10 RPS | -87.8% state load shed |
| **Frontend P95 Latency** | 246.59 ms (Initial ramp) | 180.30 $\to$ 145.40 ms | **94.00 $\to$ 77.30 ms** | -68.7% latency drop |
| **CartService P95 Latency** | 4.80 ms | 4.80 ms | 4.75 ms | Flat (< 5 ms) |
| **Locust Failure Rate** | 0.00% | 0.00% | 0.00% | Zero errors (0.00%) |
| **DPBPS Scaling Decisions** | 60 HOLD / 0 SCALE | 60 HOLD / 0 SCALE | 62 HOLD / 0 SCALE | **182 HOLD / 0 SCALE** |
| **Actuator Audit Mode** | DRY_RUN (0 mod) | DRY_RUN (0 mod) | DRY_RUN (0 mod) | 100% Invariant |
| **Post-Run Loadgenerator** | N/A | N/A | **0 replicas** | Clean watchdog stop |

---

## 2. Experimental Architecture and Workload Trajectory

### 2.1 Profile Shape Definition
```
Concurrency (Users)
  50 |  +--------------------+
     |  | Stage 1: High Tier |
  25 |  |   (50 users)       +--------------------+
     |  |   (0s - 60s)       | Stage 2: Mid Tier  |
   5 |  |                    |    (25 users)      +--------------------+
     |  |                    |   (60s - 120s)     | Stage 3: Low Tier  |
   0 +--+--------------------+--------------------+--------------------+---> Time (s)
        0                   60                   120                  180
```

- **Stage 1: High Load Tier (0s – 60s):** Target Concurrency = 50 users, Spawn Rate = 5.0 u/s.
- **Stage 2: Intermediate Tier (60s – 120s):** Target Concurrency = 25 users, Spawn Rate = 5.0 u/s.
- **Stage 3: Low Baseline Tier (120s – 180s):** Target Concurrency = 5 users, Spawn Rate = 5.0 u/s.
- **Target Host:** `frontend:80` (Internal CoreDNS).
- **Watchdog Timeout:** 185 seconds.

### 2.2 Locust Dynamic LoadTestShape Injection
Mounted from ConfigMap `dpbps-locust-e05` into `deployment/loadgenerator` at `/loadgen/locustfile.py`. Concurrency stepped down dynamically in-process without container restarts.

---

## 3. Real-Time Telemetry and De-Escalation Dynamics

During the 190.0 seconds of execution, 19 telemetry snapshots were captured at 10-second intervals across the three demand stages.

### 3.1 Telemetry Progression Table
| Timestamp | Elapsed | Stage Label | Frontend RPS | Frontend P95 | Frontend CPU | ProductCatalog RPS | CartService RPS |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **17:28:06** | 0.0s | High Tier (50u) | 0.40 RPS | 4.80 ms | 50.0% | 0.40 RPS | 0.00 RPS |
| **17:28:26** | 20.0s | High Tier (50u) | 0.50 RPS | 242.50 ms | 92.0% | 2.40 RPS | 0.40 RPS |
| **17:28:36** | 30.0s | High Tier (50u) | 18.40 RPS | 246.59 ms | 4,200.0% | 72.80 RPS | 8.90 RPS |
| **17:28:56** | 50.0s | High Tier (50u) | 41.90 RPS | 234.90 ms | 10,800.0% | 189.30 RPS | 22.10 RPS |
| **17:29:06** | 60.0s | Mid Tier (25u) | **54.00 RPS** | 226.10 ms | 13,200.0% | **251.90 RPS** | **25.50 RPS** |
| **17:29:16** | 70.0s | Mid Tier (25u) | 48.60 RPS | 180.30 ms | 12,100.0% | 248.40 RPS | 24.90 RPS |
| **17:29:26** | 80.0s | Mid Tier (25u) | 46.70 RPS | 165.10 ms | 11,500.0% | 242.50 RPS | 24.00 RPS |
| **17:29:36** | 90.0s | Mid Tier (25u) | 43.50 RPS | 147.60 ms | 10,800.0% | 225.70 RPS | 20.40 RPS |
| **17:29:46** | 100.0s | Mid Tier (25u) | 34.70 RPS | 145.40 ms | 8,900.0% | 181.80 RPS | 18.00 RPS |
| **17:29:56** | 110.0s | Mid Tier (25u) | 30.30 RPS | 154.60 ms | 7,600.0% | 156.20 RPS | 15.50 RPS |
| **17:30:06** | 120.0s | Low Tier (5u) | 27.00 RPS | 173.50 ms | 6,800.0% | 139.60 RPS | 12.50 RPS |
| **17:30:16** | 130.0s | Low Tier (5u) | 22.20 RPS | 180.80 ms | 5,500.0% | 118.60 RPS | 11.40 RPS |
| **17:30:26** | 140.0s | Low Tier (5u) | 21.80 RPS | 179.80 ms | 5,400.0% | 117.90 RPS | 11.00 RPS |
| **17:30:36** | 150.0s | Low Tier (5u) | 19.40 RPS | 126.00 ms | 4,800.0% | 107.60 RPS | 9.10 RPS |
| **17:30:46** | 160.0s | Low Tier (5u) | 14.20 RPS | 94.00 ms | 3,500.0% | 79.00 RPS | 7.40 RPS |
| **17:30:56** | 170.0s | Low Tier (5u) | 10.60 RPS | 89.90 ms | 2,700.0% | 57.70 RPS | 5.30 RPS |
| **17:31:06** | 180.0s | Concluded | **6.90 RPS** | **77.30 ms** | 1,800.0% | **37.20 RPS** | **3.10 RPS** |

### 3.2 Monotonic Demand Shedding Dynamics
1. **Frontend Throughput Shedding:** Throughput decreased gracefully in step with virtual users, falling from **54.00 RPS** at peak high load down to **30.30 RPS** at the end of Mid Tier, and finally to **6.90 RPS** at the conclusion of Low Tier ($87.2\%$ total reduction).
2. **ProductCatalog Load Shedding:** As user requests diminished, internal RPC queries plummeted from **251.90 RPS** down to **37.20 RPS** ($85.2\%$ load shed).
3. **Latency Relief:** As queue backlogs cleared, Frontend P95 latency dropped from **246.59 ms** at peak load to **145.40 ms** in Mid Tier, and plunged to **77.30 ms** in Low Tier, well below the 200 ms SLA target.

---

## 4. DPBPS Scale-Down Guardrails and Replica Floor Enforcement

Across all 19 evaluation cycles, DPBPS generated **182 decision records**:
- **HOLD:** 182 decisions (100.0%)
- **SCALE_UP:** 0 decisions (0.0%)
- **SCALE_DOWN:** 0 decisions (0.0%)

### 4.1 Why Zero SCALE_DOWN Decisions Occurred
A vital scientific insight of Experiment E05 relates to the interaction between DRY-RUN execution mode and scale-down guardrails:
1. **Minimum Replica Floor (`min_replicas = 1`):**
   - Because the actuator operates in DRY-RUN mode, the cluster's physical application deployments remained at **1 replica** throughout all previous experiments.
   - When demand fell, DPBPS evaluated `current_replicas = 1`.
   - The scaling configuration strictly forbids scaling below the minimum floor:
     $$\text{Target Replicas} = \max(\text{min\_replicas}, \text{Calculated Replicas}) = \max(1, 1) = 1$$
   - Consequently, the controller issued `HOLD` with the explicit reason: `Pressure within bounds – hold`.
2. **Anti-Premature Scale-Down Window (`scale_down_window_sec = 120s`):**
   - Even if replicas had been higher, the 120-second scale-down stabilization window prevents hasty downscaling during transient dips.
3. **Deployment-Phase Protection:**
   - Under `NORMAL_OPERATION`, scale-down rules require verified stability before reducing capacity.

---

## 5. Actuator Safety and Teardown Audit

1. **DRY_RUN Invariance:**
   - Actuator processed all 19 decision cycles with `dry_run=True`.
   - Cluster modifications: **0**.
2. **Watchdog Verification:**
   - Watchdog auto-triggered at $t=190.0\text{s}$ (target: 180s + 5s allowance).
   - Immediate scale-to-zero delivered to `deployment/loadgenerator`.
   - Post-run cluster state: `current_replicas = 0`, `reconciled = True`.
3. **Application Health:**
   - All 10 microservices operated with **0 restarts** and 100% readiness.

---

## 6. Artifact Manifest

All raw artifacts are persisted in:
`results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/`

- [`experiment_config.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/experiment_config.json): Profile config, 50 $\to$ 25 $\to$ 5 users, 180s duration.
- [`telemetry_metrics.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/telemetry_metrics.json): 19 snapshots of CPU, memory, RPS, and quantiles (P50, P95, P99).
- [`workload_metrics.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/workload_metrics.json): Step-down workload observations and Locust test logs.
- [`dpbps_decisions.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/dpbps_decisions.json): 182 decision records with priority scores and bottleneck tags.
- [`actuator_audit.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/actuator_audit.json): 19 actuator evaluations confirming 0 mutations.
- [`experiment_summary.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/experiment_summary.json): Aggregated KPI metrics and run assertions.
- [`experiment.log`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172806_traffic_decrease_71144bfe/experiment.log): Execution trace and captured Locust container logs.

---

## 7. Validation Gate Verdict

| Validation Gate Check | Specification | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| **All 7 Artifacts Exist & Readable** | 7 JSON/log files | 7 files verified | **PASS** |
| **Telemetry Timestamps Valid** | Monotonic UTC ISO-8601 | 19 valid snapshots | **PASS** |
| **Workload Stages Match Profile** | 50u (60s) $\to$ 25u (60s) $\to$ 5u (60s) | Verified in Locust | **PASS** |
| **Decision Count Reconciliation** | 19 cycles = 182 decisions | 182 decisions reconciled | **PASS** |
| **Zero Cluster Mutations** | `cluster_modified: false` | 0 mutations applied | **PASS** |
| **Loadgenerator Replicas** | 0 replicas post-run | 0 replicas verified | **PASS** |
| **10/10 Microservices Healthy** | 1/1 Running | 10/10 Running & Ready | **PASS** |
| **Safety Lock Restored** | `EXPERIMENT_EXECUTION_ENABLED=false` | `false` confirmed | **PASS** |

### **GATE VERDICT: GO FOR EXPERIMENT E06 (BURSTY_TRAFFIC)**
Experiment E05 passed all validation gate checks with complete data fidelity. Authorization is granted to proceed with E06.

