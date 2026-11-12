# STAGE 16 — EXPERIMENT CONFIGURATION REPORT
**Experimental Matrix, Workload Profiles & Test Parameter Specifications**  
**DPBPS Autoscaling Framework — Google Online Boutique Microservices**  
**Workspace:** `D:\CIS\Deployment Aware AAutoscaling Platform` | **Branch:** `master`

---

## 1. EXPERIMENTAL MATRIX SPECIFICATION

The Stage 16 evaluation is structured as an **$8 \times 4$ factorial design** (8 scenarios across 4 scaling policies) with **5 independent repetitions** per configuration, yielding **160 complete scenario evaluation runs**.

```
+-----------------------------------------------------------------------------------------+
|                              Stage 16 Experimental Matrix                               |
+-----------+-----------------------------------+--------------------+--------------------+
| Scenario  | Workload / Perturbation Type      | Target System      | Primary Evaluation |
+-----------+-----------------------------------+--------------------+--------------------+
| S1 (E01)  | Low-Load Steady-State (10 Users)  | 10 Boutique Serv.  | Over-provisioning  |
| S2 (E02)  | Gradual Ramp (10 -> 50 Users)     | 10 Boutique Serv.  | Scale-Up Delay     |
| S3 (E03)  | Sudden Traffic Spike (0->100 Usr) | 10 Boutique Serv.  | SLA Preservation   |
| S4 (E04)  | Sustained High Load (100 Users)   | 10 Boutique Serv.  | Resource Efficiency|
| S5 (E05)  | Traffic Reduction & Recovery      | 10 Boutique Serv.  | Stabilization / Flap|
| S6 (E07)  | CI/CD Rollout (ACTIVE_DEPLOYMENT) | ProductCatalog     | Downscale Suppression|
| S7 (E08)  | Stale Telemetry (>60s Dropout)    | Cluster Telemetry  | Fail-Closed Safety |
| S8 (E09)  | Scaling Failure & Probe Timeout   | ProductCatalog     | Automated Rollback |
+-----------+-----------------------------------+--------------------+--------------------+
```

---

## 2. DETAILED SCENARIO SPECIFICATIONS

### Scenario S1 — Low-Load Steady-State Workload (E01)
- **Profile:** 10 continuous simulated users browsing the storefront and catalog.
- **Duration:** 140 evaluation seconds (14 evaluation cycles at 10s intervals).
- **Workload Concurrency:** Constant 10 users; spawn rate 2 users/sec.
- **Objective:** Evaluate baseline stability and confirm that policies do not suffer from false-positive scaling actions or over-provisioning during nominal low-load conditions.

### Scenario S2 — Gradually Increasing Workload (E02)
- **Profile:** Linear traffic ramp from 10 to 50 users at 2 users/second.
- **Duration:** 190 evaluation seconds (19 evaluation cycles at 10s intervals).
- **Objective:** Measure scale-up reaction time ($t_{\text{first\_up}}$) as CPU and latency approach watermark boundaries.

### Scenario S3 — Sudden Traffic Spike (E03)
- **Profile:** Immediate step spike from 0 to 100 users within 5 seconds.
- **Duration:** 130 evaluation seconds (13 evaluation cycles).
- **Objective:** Evaluate resilience against severe tail latency degradation (P95/P99 latency) and verify whether the controller prevents HTTP 5xx error bursts.

### Scenario S4 — Sustained High Workload (E04)
- **Profile:** 100 concurrent users sustained continuously for 230 seconds.
- **Duration:** 230 evaluation seconds (23 evaluation cycles).
- **Objective:** Measure peak replica provisioning, steady-state throughput, and total replica-hour resource consumption under persistent saturation.

### Scenario S5 — Traffic Reduction and Recovery (E05)
- **Profile:** High load (100 users) dropped abruptly to 0 users, followed by a 120-second cooldown recovery period.
- **Duration:** 190 evaluation seconds (19 evaluation cycles).
- **Objective:** Measure scale-down hysteresis, cooldown compliance, and verify absence of rapid replica oscillation (thrashing).

### Scenario S6 — CI/CD Active Deployment Workload (E07)
- **Profile:** Continuous moderate traffic (35 RPS) while target service `productcatalogservice` undergoes a rolling deployment (`ACTIVE_DEPLOYMENT` phase).
- **Duration:** 300 seconds (30 evaluation cycles).
- **Perturbation:** Replicas report temporary CPU initialization dips and container startup latency.
- **Objective:** Verify whether the scaling policy avoids premature scale-down and prevents pod evictions during in-flight rolling updates.

### Scenario S7 — Missing and Stale Telemetry Scenario (E08)
- **Profile:** Steady traffic with an intentional telemetry collection dropout lasting 8 consecutive cycles (80 seconds), exceeding the 60-second freshness threshold.
- **Duration:** 200 seconds (20 evaluation cycles).
- **Objective:** Confirm fail-closed behavior. Verify that the controller refuses to interpret missing metrics as 0.0 utilization (which would cause catastrophic downscaling).

### Scenario S8 — Scaling Failure and Rollback Recovery (E09)
- **Profile:** Target service is commanded to scale up from 1 to 2 replicas, but the new pod fails readiness probes (simulated probe failure / image backoff).
- **Duration:** 120 seconds.
- **Objective:** Validate actuator post-action readiness engine and measure automated rollback execution time to restore the known steady-state baseline.

---

## 3. WORKLOAD GENERATION & TRAFFIC DISTRIBUTION

The workload models authentic user sessions against the **Google Online Boutique** web store:

| User Task | Endpoint / Method | Relative Weight | Primary Service Exercised |
|---|---|:---:|---|
| `browseProduct` | `GET /product/{id}` | **10** (52.6%) | `productcatalogservice` via `frontend` |
| `viewCart` | `GET /cart` | **3** (15.8%) | `cartservice` |
| `setCurrency` | `POST /setCurrency` | **2** (10.5%) | `currencyservice` |
| `addToCart` | `POST /cart` | **2** (10.5%) | `cartservice` + `productcatalogservice` |
| `index` | `GET /` | **1** (5.3%) | `productcatalogservice` + `recommendationservice` |
| `checkout` | `POST /cart/checkout` | **1** (5.3%) | `checkoutservice` + all 6 downstreams |

Over **73.7%** of all generated HTTP transactions directly traverse and exercise `productcatalogservice`, providing an optimal experimental channel for isolated bottleneck evaluation.

---

## 4. MEASUREMENT PARAMETERS & SAFETY CONSTRAINTS

- **Sampling Interval:** 10.0 seconds per snapshot cycle.
- **SLO Definitions:**
  - P95 Response Latency SLO: **$\le 500\text{ ms}$**.
  - Cluster Error Rate SLO: **$\le 1.0\%$** of total requests.
- **Replica Boundaries:**
  - Candidate Testing: $R_{min} = 1$, $R_{max} = 3$, Max Delta $|\Delta R| = 1$.
  - Global Framework Bounds: $R_{min} = 1$, $R_{max} = 10$, Max Delta $|\Delta R| = 2$.
- **Stabilization Timers:**
  - Scale-up delay: Immediate (0s).
  - Scale-down stabilization: 60 seconds (4 consecutive cycles).
- **Fail-Safe Gates:**
  - `SCALING_ENABLED` default: `False`.
  - Actuator default: `dry_run=True`.
  - Emergency stop available across UI, REST API, and CLI.

