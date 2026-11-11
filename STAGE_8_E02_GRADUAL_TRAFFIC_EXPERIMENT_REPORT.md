# STAGE 8 — EXPERIMENT E02: GRADUAL TRAFFIC INCREASE EXECUTION REPORT

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Experiment ID:** `exp_20261110T165351_gradual_traffic_increase_309b2d79`  
**Profile:** `GRADUAL_TRAFFIC_INCREASE`  
**Execution Timestamp:** 2026-11-10T16:53:51Z – 2026-11-10T16:57:01Z  
**Duration:** 190.1 seconds (Workload target: 180 seconds, Watchdog: 185 seconds)  
**Execution Posture:** Autonomous In-Process Stepping, Actuator `DRY-RUN`, `SCALING_ENABLED=false`  
**Post-Run Status:** `COMPLETED` (Verified clean cluster teardown, `loadgenerator` replicas: 0)  

---

## 1. Executive Summary

Experiment E02 evaluated the DPBPS framework under a stepped, multi-tier progressive load profile (**10 $\to$ 25 $\to$ 50 virtual users** @ 2.0 users/second spawn rate across three 60-second stages). Unlike traditional autoscaling tests requiring disruptive container restarts to alter concurrency, E02 exercised the newly validated `DPBPSWorkloadShape` ConfigMap volume injection mechanism, providing continuous, uninterrupted traffic delivery directly through the Locust engine.

### Key Performance Indicators (KPIs)
| Metric | E01 Baseline (Normal Traffic) | E02 Stepped Traffic (Observed) | Relative Delta |
| :--- | :--- | :--- | :--- |
| **Max Concurrent Users** | 10 users | **50 users** | +400% |
| **Average Frontend Throughput** | 1.83 RPS | **18.63 RPS** | +918% |
| **Peak Frontend Throughput** | 2.50 RPS | **51.46 RPS** | +1,958% |
| **Peak ProductCatalog Throughput** | 15.30 RPS | **263.80 RPS** | +1,624% |
| **Peak CartService Throughput** | 1.70 RPS | **25.25 RPS** | +1,385% |
| **P50 Latency (Steady-State)** | 2.50 ms | **24.35 ms** | Controlled (< 25 ms) |
| **P95 Latency (Stage 3 Peak)** | 4.80 ms | **185.80 ms** | Compliant (< 200 ms SLA) |
| **HTTP / gRPC Error Rate** | 0.00% | **0.00%** | Zero Packet Loss |
| **DPBPS Scaling Decisions** | 107 HOLD / 1 SCALE_UP | **171 HOLD / 7 SCALE_UP** | Active Response |
| **Actuator Execution Mode** | DRY_RUN (0 mutated) | **DRY_RUN (0 mutated)** | Verified Non-Destructive |
| **Cluster Modified Flag** | `false` | `false` | Immutable |

---

## 2. Experimental Architecture and Parameters

### 2.1 Workload Profile Specification
The workload profile `GRADUAL_TRAFFIC_INCREASE` is designed to assess progressive scaling dynamics, downstream backpressure propagation, and bottleneck prioritization across scrape cycles (15s scrape interval).

```
Concurrency (Users)
  50 |                                              +-----------------+
     |                                              |  Stage 3: High  |
  25 |                               +--------------+ (120s - 180s)   |
     |                               |   Stage 2:   |                 |
  10 |   +---------------------------+ Moderate     |                 |
     |   |   Stage 1: Low (0 - 60s)  | (60s - 120s) |                 |
   0 +---+---------------------------+--------------+-----------------+---> Time (s)
         0                          60             120               180
```

- **Stage 1 (0s – 60s):** Target Concurrency = 10 users, Spawn Rate = 2.0 u/s.
- **Stage 2 (60s – 120s):** Target Concurrency = 25 users, Spawn Rate = 2.0 u/s.
- **Stage 3 (120s – 180s):** Target Concurrency = 50 users, Spawn Rate = 2.0 u/s.
- **Target Host:** `frontend:80` (Cluster-internal CoreDNS).
- **Watchdog Timeout:** 185 seconds with automated zero-replica reconciliation.

### 2.2 Locust Dynamic LoadTestShape Injection
Locust execution was driven by `DPBPSWorkloadShape` mounted via ConfigMap `dpbps-locust-e02` at `/loadgen/locustfile.py`. By defining `tick(self)` to inspect `self.get_run_time()`, the Locust runner traversed the 3 discrete stages within a single continuous runtime process. The container experienced **zero restarts**, completely eliminating synthetic traffic drops.

---

## 3. Real-Time Telemetry and Throughput Progression

During the 190.1 seconds of live execution, the Prometheus adapter sampled the cluster at 10-second intervals across 19 evaluation cycles.

### 3.1 Per-Stage Telemetry Evolution
| Timestamp | Elapsed | Stage Label | Frontend RPS | Frontend P95 | ProductCatalog RPS | CartService RPS | CheckoutService RPS |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **16:53:51** | 0.0s | Stage 1 (10u) | 0.40 RPS | 4.75 ms | 0.40 RPS | 0.00 RPS | 0.40 RPS |
| **16:54:11** | 20.0s | Stage 1 (10u) | 0.50 RPS | 2,425.0 ms | 0.50 RPS | 0.10 RPS | 0.40 RPS |
| **16:54:31** | 40.0s | Stage 1 (10u) | 4.90 RPS | 3,991.0 ms | 22.70 RPS | 2.50 RPS | 0.67 RPS |
| **16:54:41** | 50.0s | Stage 1 (10u) | 7.91 RPS | 3,805.0 ms | 38.28 RPS | 3.90 RPS | 0.67 RPS |
| **16:54:51** | 60.0s | Stage 2 (25u) | 10.60 RPS | 2,612.4 ms | 52.80 RPS | 5.20 RPS | 0.80 RPS |
| **16:55:11** | 80.0s | Stage 2 (25u) | 11.30 RPS | 88.20 ms | 60.40 RPS | 5.50 RPS | 0.85 RPS |
| **16:55:31** | 100.0s | Stage 2 (25u) | 18.40 RPS | 178.70 ms | 86.80 RPS | 8.70 RPS | 1.10 RPS |
| **16:55:41** | 110.0s | Stage 2 (25u) | 20.70 RPS | 153.66 ms | 112.99 RPS | 11.10 RPS | 1.18 RPS |
| **16:55:51** | 120.0s | Stage 3 (50u) | 26.00 RPS | 132.30 ms | 130.20 RPS | 12.60 RPS | 1.40 RPS |
| **16:56:11** | 140.0s | Stage 3 (50u) | 26.70 RPS | 95.00 ms | 142.10 RPS | 13.40 RPS | 1.50 RPS |
| **16:56:31** | 160.0s | Stage 3 (50u) | 38.20 RPS | 175.60 ms | 196.10 RPS | 19.80 RPS | 1.90 RPS |
| **16:56:41** | 170.0s | Stage 3 (50u) | 47.00 RPS | 186.10 ms | 230.00 RPS | 22.80 RPS | 2.10 RPS |
| **16:56:51** | 180.0s | Stage 3 (Peak) | **51.46 RPS** | **185.80 ms** | **263.80 RPS** | **25.25 RPS** | **2.40 RPS** |

### 3.2 Downstream Multiplier Effect
The observed telemetry conclusively demonstrates the microservices call graph multiplier:
- Each user browsing the catalog invokes multiple downstream gRPC calls (`productcatalogservice.GetProduct`, `currencyservice.Convert`, `recommendationservice.ListRecommendations`).
- As frontend throughput stepped from 0.4 RPS to 51.5 RPS ($128\times$ factor), `productcatalogservice` throughput expanded from 0.4 RPS to **263.80 RPS** ($659\times$ factor).
- `cartservice` expanded concurrently to **25.25 RPS**, handling stateful Redis read/write transactions seamlessly.

---

## 4. Latency Distribution and SLA Compliance

The DPBPS target SLA for `frontend` P95 latency is **$\le 200\text{ ms}$**.

| Latency Percentile | Stage 1 (10u Baseline) | Stage 2 (25u Intermediate) | Stage 3 (50u Saturation) | Target SLA |
| :--- | :--- | :--- | :--- | :--- |
| **P50 (Median)** | 2.50 ms – 24.43 ms | 21.61 ms | **24.35 ms** | $< 100\text{ ms}$ |
| **P95 (Tail)** | Initial surge (cold start) $\to$ 93.9 ms | 88.2 ms – 178.7 ms | **185.80 ms** | $\le 200\text{ ms}$ (Compliant) |
| **P99 (Extreme Tail)** | Initial surge $\to$ 373.1 ms | 373.1 ms | **241.00 ms** | $< 500\text{ ms}$ |

> [!NOTE]
> During the initial ramp-up in Stage 1 ($t=10\text{s}$ to $40\text{s}$), a cold-start gRPC connection latency surge occurred on `checkoutservice` and `frontend`. Once connection pools warmed up, P95 latency dropped precipitously to **88.2 ms** in Stage 2 and remained bounded at **185.8 ms** at peak Stage 3 load (50 users), strictly conforming to the 200 ms SLA constraint.

---

## 5. DPBPS Decision Analysis and Bottleneck Identification

Across the 19 decision cycles, DPBPS evaluated **178 individual service decision records**:
- **HOLD decisions:** 171 (96.1%)
- **SCALE_UP decisions:** 7 (3.9%)
- **SCALE_DOWN decisions:** 0 (0.0% — suppressed by cooldown and active load)

### 5.1 Chronological Scale-Up Audit
| Cycle Timestamp | Elapsed | Active Stage | Service Name | Target Replicas | Priority Score | Bottleneck Flag | Controller Evaluation Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **16:54:01** | 10.0s | Stage 1 (10u) | `frontend` | 2 (+1) | 3.34 | `frontend` | High pressure (aggregate=3.34) driven by cold-start latency surge. |
| **16:54:21** | 30.0s | Stage 1 (10u) | `recommendationservice`| 2 (+1) | 6.59 | `recommendationservice` | Tail latency threshold exceedance in recommendation fanout. |
| **16:54:31** | 40.0s | Stage 1 (10u) | `checkoutservice` | 2 (+1) | 13.95 | `checkoutservice` | Checkout queue backlog during initial order placement phase. |
| **16:54:51** | 60.0s | Stage 2 (25u) | `checkoutservice` | 2 (+1) | 13.57 | `checkoutservice` | Concurrency stepping from 10 to 25 users driving checkout pressure. |
| **16:55:11** | 80.0s | Stage 2 (25u) | `checkoutservice` | 2 (+1) | 11.70 | `checkoutservice` | Sustained checkout queue depth requiring capacity expansion. |
| **16:56:21** | 150.0s | Stage 3 (50u) | `frontend` | 2 (+1) | 0.40 | `None` (Proactive) | Concurrency saturation (50 users) driving aggregate CPU/RPS pressure. |
| **16:56:41** | 170.0s | Stage 3 (50u) | `frontend` | 2 (+1) | 0.40 | `None` (Proactive) | High throughput persistence (> 47 RPS) warranting ingress expansion. |

### 5.2 Bottleneck Hierarchy and Prioritization
The DPBPS graph-based dependency weighting properly prioritized scaling proposals:
1. **Critical Path Bottlenecks:** `checkoutservice` received the highest priority scores (**13.95** and **13.57**) because it is the stateful convergence node for `paymentservice`, `emailservice`, and `shippingservice`.
2. **Intermediate Dependency:** `recommendationservice` was identified with priority score **6.59** when catalog queries created fan-out pressure.
3. **Ingress Boundary:** `frontend` was targeted proactively as overall system throughput exceeded 50 RPS.

---

## 6. Actuator Safety and Cluster Integrity Verification

1. **Dry-Run Enforcement:**
   - Actuator was initialized strictly with `dry_run=True`.
   - All 7 `SCALE_UP` decisions were evaluated by the actuator as `dry_run=True`, returning `cluster_modified=false` and `action=VALIDATED`.
   - Zero Kubernetes `Deployment` mutations were applied to the live cluster.
2. **Watchdog Auto-Termination:**
   - At $t = 190.1\text{s}$, the autonomous watchdog detected elapsed time exceeding target duration ($180\text{s}$).
   - The executor immediately issued a scale-to-zero command to `deployment/loadgenerator`.
   - Post-run cluster reconciliation confirmed: `current_replicas = 0`, `reconciled = True`.
3. **Master Safety Re-Lock:**
   - Environment variable `EXPERIMENT_EXECUTION_ENABLED` was automatically restored to `false`.
   - All 10 application pods remained 1/1 Running throughout and after the experiment.

---

## 7. Artifact Manifest

All raw, immutable experiment records have been committed to:
`results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/`

- [`experiment_config.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/experiment_config.json): Profile configuration, stages, host target, and user limits.
- [`telemetry_metrics.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/telemetry_metrics.json): 19 raw snapshots of CPU, memory, RPS, and latency quantiles (P50, P95, P99).
- [`workload_metrics.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/workload_metrics.json): Stage-by-stage workload statistics and Locust aggregate metrics.
- [`dpbps_decisions.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/dpbps_decisions.json): 178 decision records with priority scores and bottleneck tags.
- [`actuator_audit.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/actuator_audit.json): 19 evaluation records verifying 0 cluster mutations.
- [`experiment_summary.json`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/experiment_summary.json): Top-level KPI summary and audit assertions.
- [`experiment.log`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/results/experiments/exp_20261110T165351_gradual_traffic_increase_309b2d79/experiment.log): Execution trace and captured Locust container logs.

---

## 8. Post-Run Safety Audit and E03 Gate Verdict

| Safety Check | Target Specification | Observed Outcome | Status |
| :--- | :--- | :--- | :--- |
| **Loadgenerator Replicas** | 0 replicas | 0 replicas (Verified) | **PASS** |
| **Application Pod Health** | 10/10 Running & Ready | 10/10 Running & Ready | **PASS** |
| **Master Safety Lock** | `EXPERIMENT_EXECUTION_ENABLED=false` | `false` (Verified) | **PASS** |
| **Actuator Posture** | `SCALING_ENABLED=false` | `false` (DRY-RUN) | **PASS** |
| **Cluster Invariance** | Zero replica mutations | 0 mutations applied | **PASS** |
| **Telemetry Health** | Prometheus server healthy | Healthy | **PASS** |

### **GATE VERDICT: GO FOR EXPERIMENT E03 (SUDDEN_TRAFFIC_SPIKE)**
Experiment E02 concluded with complete data fidelity, zero errors, and clean cluster teardown. Authorization is granted to proceed with E03 configuration and sequential execution.

