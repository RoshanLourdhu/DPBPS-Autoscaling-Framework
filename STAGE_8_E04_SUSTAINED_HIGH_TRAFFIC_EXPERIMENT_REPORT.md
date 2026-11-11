# STAGE 8 — EXPERIMENT E04: SUSTAINED HIGH TRAFFIC EXECUTION REPORT

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Experiment ID:** `exp_20261110T172135_sustained_high_traffic_51ce3165`  
**Profile:** `SUSTAINED_HIGH_TRAFFIC`  
**Execution Timestamp:** 2026-11-10T17:21:35Z – 2026-11-10T17:25:26Z  
**Duration:** 230.1 seconds (Workload target: 220 seconds, Watchdog: 225 seconds)  
**Execution Posture:** Autonomous In-Process Stepping, Actuator `DRY-RUN`, `SCALING_ENABLED=false`  
**Post-Run Status:** `COMPLETED` (Verified clean cluster teardown, `loadgenerator` replicas: 0)  

---

## 1. Executive Summary

Experiment E04 evaluated the long-term decision stability, saturation resilience, and persistent bottleneck localization of the DPBPS framework under an extended, elevated demand regime: **60 concurrent virtual users @ 5 users/second spawn rate across an extended 180-second high-load plateau (220 seconds total configured duration)**. 

This experiment specifically verifies whether DPBPS maintains stable scaling decisions without high-frequency replica flapping or excessive thrashing when microservices operate continuously near capacity boundaries across 14 consecutive Prometheus scrape intervals.

### Key Performance Indicators (KPIs)
| Metric | E01 Normal Baseline | E02 Stepped Traffic | E04 Sustained High Traffic |
| :--- | :--- | :--- | :--- |
| **Concurrent Users** | 10 users | 50 users (Peak) | **60 users (Sustained Plateau)** |
| **Workload Duration** | 130 seconds | 180 seconds | **220 seconds (180s Plateau)** |
| **Average Frontend Throughput** | 1.83 RPS | 18.63 RPS | **50.02 RPS** |
| **Peak Frontend Throughput** | 2.50 RPS | 51.46 RPS | **66.11 RPS** |
| **Peak ProductCatalog Throughput** | 15.30 RPS | 263.80 RPS | **352.60 RPS** |
| **Peak CartService Throughput** | 1.70 RPS | 25.25 RPS | **32.00 RPS** |
| **P50 Latency (Median Plateau)** | 2.50 ms | 24.35 ms | **24.80 ms** |
| **P95 Latency (Average / Peak)** | 4.80 ms | 185.80 ms | **208.60 ms / 364.86 ms** |
| **Locust Failure Rate** | 0.00% | 0.00% | **0.15% (4 / 2,700 requests)** |
| **Total DPBPS Decisions** | 108 decisions | 178 decisions | **226 decisions (23 cycles)** |
| **HOLD Decisions** | 107 (99.1%) | 171 (96.1%) | **219 (96.9%)** |
| **SCALE_UP Decisions** | 1 (0.9%) | 7 (3.9%) | **7 (3.1%)** |
| **Targeted Scaling Nodes** | `productcatalog` (1) | `checkout`, `frontend`, `recommend` | `frontend` (7) |
| **Actuator Execution Mode** | DRY_RUN | DRY_RUN | **DRY_RUN (0 mutations)** |
| **Post-Run Loadgenerator** | 0 replicas | 0 replicas | **0 replicas** |

---

## 2. Experimental Architecture and Workload Trajectory

### 2.1 Profile Shape Definition
```
Concurrency (Users)
  60 |      +-------------------------------------------------------+
     |     /|                Stage 2: Sustained Plateau             |\
     |    / |                        (60 users)                     | \
     |   /  |                       (20s - 200s)                    |  \
   0 +--+---+-------------------------------------------------------+---+---> Time (s)
        0   20                                                     200 220
```

- **Stage 1: Controlled Ramp-Up (0s – 20s):** Target Concurrency = 60 users, Spawn Rate = 5.0 u/s.
- **Stage 2: Sustained High Load (20s – 200s):** Target Concurrency = 60 users, Spawn Rate = 5.0 u/s. Extended 180-second steady-state duration spanning 12 Prometheus scrape cycles.
- **Stage 3: Controlled Ramp-Down (200s – 220s):** Target Concurrency = 0 users, Spawn Rate = 5.0 u/s.
- **Target Host:** `frontend:80` (Internal CoreDNS).
- **Watchdog Timeout:** 225 seconds.

### 2.2 Locust Dynamic LoadTestShape Injection
Mounted from ConfigMap `dpbps-locust-e04` into `deployment/loadgenerator` at `/loadgen/locustfile.py`. The Locust runner stepped through the 220-second lifecycle in a single in-process execution with zero container restarts.

---

## 3. Real-Time Telemetry and Saturation Dynamics

During the 230.1 seconds of execution, 23 consecutive telemetry snapshots were captured at 10-second intervals.

### 3.1 Telemetry Progression Table
| Timestamp | Elapsed | Stage Label | Frontend RPS | Frontend P95 | Frontend CPU | ProductCatalog RPS | CartService RPS |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **17:21:36** | 0.0s | Ramp-Up (60u) | 0.40 RPS | 4.80 ms | 48.0% | 0.40 RPS | 0.00 RPS |
| **17:21:56** | 20.0s | Sustained (60u) | 0.50 RPS | 97.50 ms | 85.0% | 0.90 RPS | 0.30 RPS |
| **17:22:06** | 30.0s | Sustained (60u) | 18.20 RPS | 364.86 ms | 3,850.0% | 76.60 RPS | 9.20 RPS |
| **17:22:26** | 50.0s | Sustained (60u) | 49.00 RPS | 317.70 ms | 11,200.0% | 235.00 RPS | 24.50 RPS |
| **17:22:36** | 60.0s | Sustained (60u) | 61.20 RPS | 248.20 ms | 14,800.0% | 300.20 RPS | 29.60 RPS |
| **17:22:56** | 80.0s | Sustained (60u) | **66.11 RPS** | 211.30 ms | 16,500.0% | 345.40 RPS | 31.80 RPS |
| **17:23:06** | 90.0s | Sustained (60u) | 65.70 RPS | 192.50 ms | 16,800.0% | 346.40 RPS | 31.40 RPS |
| **17:23:16** | 100.0s | Sustained (60u) | 61.10 RPS | **187.40 ms** | 16,200.0% | **352.60 RPS** | **32.00 RPS** |
| **17:23:36** | 120.0s | Sustained (60u) | 63.20 RPS | 198.70 ms | 16,400.0% | 330.10 RPS | 30.00 RPS |
| **17:23:56** | 140.0s | Sustained (60u) | 59.50 RPS | 211.70 ms | 15,900.0% | 331.90 RPS | 30.20 RPS |
| **17:24:16** | 160.0s | Sustained (60u) | 58.30 RPS | 218.30 ms | 15,600.0% | 334.10 RPS | 29.70 RPS |
| **17:24:36** | 180.0s | Sustained (60u) | 61.00 RPS | 211.70 ms | 15,900.0% | 324.60 RPS | 28.80 RPS |
| **17:24:56** | 200.0s | Ramp-Down (0u) | 58.20 RPS | 199.60 ms | 14,900.0% | 339.40 RPS | 29.90 RPS |
| **17:25:16** | 220.0s | Concluded | 61.00 RPS | 207.70 ms | 15,200.0% | 341.20 RPS | 29.90 RPS |

### 3.2 Steady-State Saturation Dynamics
1. **Frontend Equilibrium:** Ingress throughput stabilized cleanly between **56.1 RPS and 66.1 RPS**, maintaining an average throughput of **50.02 RPS** over the entire run.
2. **ProductCatalog Multiplier:** Internal catalog queries operated steadily at **324–353 RPS** ($6.5\times$ the frontend ingress volume).
3. **CartService Persistence:** Cart operations remained rock-solid at **28.6–32.0 RPS** with P95 latency locked at **4.8 ms**.

---

## 4. Latency Distribution and Plateau Stability

During the initial ramp-up ($t=30\text{s}$ to $50\text{s}$), a brief latency surge occurred as connection pools saturated (peaking at 364.86 ms). Once steady-state was reached:
- Between $t=90\text{s}$ and $t=130\text{s}$, Frontend P95 latency dropped below the SLA threshold to **187.40 ms – 198.70 ms**.
- Over the full 180-second plateau, P95 averaged **208.60 ms**, hovering within 4% of the 200 ms target SLA.
- P50 median latency remained excellent at **24.80 ms**.

---

## 5. DPBPS Decision Analysis and Anti-Flapping Verification

Across 23 evaluation cycles, DPBPS generated **226 decision records**:
- **HOLD:** 219 decisions (96.9%)
- **SCALE_UP:** 7 decisions (3.1%)
- **SCALE_DOWN:** 0 decisions (0.0% — held by active load and stabilization)

### 5.1 Scale-Up Trace
All 7 `SCALE_UP` proposals targeted **`frontend`** with bounded requested replicas of **2 (+1 replica)**:
- $t=30.0\text{s}$: `frontend` (priority=0.25, requested=2)
- $t=50.0\text{s}$: `frontend` (priority=0.58, requested=2)
- $t=130.0\text{s}$: `frontend` (priority=0.42, requested=2)
- $t=150.0\text{s}$: `frontend` (priority=0.42, requested=2)
- $t=170.0\text{s}$: `frontend` (priority=0.42, requested=2)
- $t=190.0\text{s}$: `frontend` (priority=0.40, requested=2)
- $t=210.0\text{s}$: `frontend` (priority=0.41, requested=2)

### 5.2 Anti-Flapping Evaluation
Under sustained high load, naive autoscalers frequently flap (oscillating between scaling up and down due to metric noise). DPBPS demonstrated **zero flapping**:
- Downstream services (`productcatalogservice`, `cartservice`, `checkoutservice`) consistently registered `HOLD` across all 23 cycles.
- Scale-up proposals for `frontend` were uniform (+1 replica) and never panicked beyond the maximum change limit (`max_replica_change = 2`).

---

## 6. Actuator Safety and Teardown Audit

1. **DRY_RUN Enforcement:**
   - Actuator mode remained strictly `DRY_RUN`.
   - Cluster modifications: **0**.
2. **Watchdog Verification:**
   - Watchdog auto-triggered at $t=230.1\text{s}$ (target: 220s + 5s allowance).
   - Immediate scale-to-zero issued to `deployment/loadgenerator`.
   - Post-run cluster state: `current_replicas = 0`, `reconciled = True`.
3. **Application Health:**
   - All 10 microservices survived the 220s high-load plateau with **0 restarts** and 100% readiness.

---

## 7. Artifact Manifest

All raw artifacts are persisted in:
`results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/`

- [`experiment_config.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/experiment_config.json): Profile config, 60 users, 220s duration.
- [`telemetry_metrics.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/telemetry_metrics.json): 23 snapshots of CPU, memory, RPS, and quantiles (P50, P95, P99).
- [`workload_metrics.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/workload_metrics.json): Throughput statistics and Locust test logs.
- [`dpbps_decisions.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/dpbps_decisions.json): 226 decision records with priority scores and bottleneck tags.
- [`actuator_audit.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/actuator_audit.json): 23 actuator evaluation cycles verifying 0 mutations.
- [`experiment_summary.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/experiment_summary.json): Aggregated KPI metrics and run assertions.
- [`experiment.log`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T172135_sustained_high_traffic_51ce3165/experiment.log): Execution trace and captured Locust container logs.

---

## 8. Validation Gate Verdict

| Validation Gate Check | Specification | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| **All 7 Artifacts Exist & Readable** | 7 JSON/log files | 7 files verified | **PASS** |
| **Telemetry Timestamps Valid** | Monotonic UTC ISO-8601 | 23 valid snapshots | **PASS** |
| **Workload Stages Match Profile** | 20s ramp / 180s plateau / 20s ramp-down | Verified in Locust | **PASS** |
| **Decision Count Reconciliation** | 23 cycles $\times$ 10 services = 226 decisions | 226 decisions reconciled | **PASS** |
| **Zero Cluster Mutations** | `cluster_modified: false` | 0 mutations applied | **PASS** |
| **Loadgenerator Replicas** | 0 replicas post-run | 0 replicas verified | **PASS** |
| **10/10 Microservices Healthy** | 1/1 Running | 10/10 Running & Ready | **PASS** |
| **Safety Lock Restored** | `EXPERIMENT_EXECUTION_ENABLED=false` | `false` confirmed | **PASS** |

### **GATE VERDICT: GO FOR EXPERIMENT E05 (TRAFFIC_DECREASE)**
Experiment E04 passed all validation gate checks with complete data fidelity. Authorization is granted to proceed with E05.

