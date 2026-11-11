# STAGE 9.4 — COMPARATIVE PERFORMANCE ANALYSIS

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Author:** Roshan Lourdhu  
**Date:** 2026-11-10  
**Phase:** 9.4 Multi-Policy Comparative Performance, Bottleneck Prioritization & Efficiency Analysis  

---

## 1. Executive Summary

This document provides a comparative performance analysis of the proposed **DPBPS** autoscaling framework against three conventional scaling methodologies: **Static Allocation**, **CPU-Threshold Reactive Scaling**, and **Conventional HPA-Style Scaling**, based on the empirical trace-replay evaluation across Experiments E01 through E06.

### Core Comparative Findings
1. **Bottleneck Specificity:** DPBPS directed **85.2% of its scale-up recommendations to `frontend`** (the proven ingress bottleneck) and **11.1% to `checkoutservice`** (the critical multi-service checkout orchestrator). In contrast, CPU-Threshold and HPA-Style misdirected **48.1% and 38.2% of their scaling actions to non-congested leaf services (`productcatalogservice` and `currencyservice`)** purely due to tight CPU reservations, despite sub-5ms latencies.
2. **Detection Velocity:** Under progressive workload expansion (E02), DPBPS issued its first scale-up recommendation at **$t=10.0\text{s}$**, detecting latency and queue pressure early. CPU-Threshold lagged by **150 seconds** ($t=160.0\text{s}$), leaving the frontend saturated throughout the first two stages.
3. **Anti-Flapping & Stability:** Under bursty traffic (E06), CPU-Threshold suffered from thrashing, generating **2 premature scale-down actions** during 20-second lull intervals. DPBPS achieved **0 scale-downs**, completely suppressing flapping while maintaining single-step bounded scale-up proposals during bursts.
4. **Over-Provisioning Suppression:** HPA-Style repeatedly escalated capacity to the **maximum limit (10 replicas)** across 5 of the 6 workloads. DPBPS constrained capacity expansion to **4 to 8 replicas**, avoiding runaway over-allocation.

---

## 2. In-Depth Decision Metrics Analysis

### 2.1 Comparative Decision Distribution Across Campaign
```
Policy Decision Proportions (1,050 Evaluations):
STATIC:        [HOLD: 1,050 (100.0%)]
CPU_THRESHOLD: [HOLD: 988 (94.1%)] [SCALE_UP: 27 (2.6%)] [SCALE_DOWN: 3 (0.3%)] [INSUFFICIENT: 32 (3.0%)]
HPA_STYLE:     [HOLD: 984 (93.7%)] [SCALE_UP: 34 (3.2%)] [SCALE_DOWN: 0 (0.0%)] [INSUFFICIENT: 32 (3.0%)]
DPBPS:         [HOLD: 991 (94.4%)] [SCALE_UP: 27 (2.6%)] [SCALE_DOWN: 0 (0.0%)] [INSUFFICIENT: 32 (3.0%)]
```

### 2.2 Responsiveness & Timing Metrics
| Evaluation Metric | Static Policy | CPU-Threshold Policy | HPA-Style Policy | Proposed DPBPS | Impact Analysis |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **E02 Stepped: Time to 1st Scale-Up** | $\infty$ (Never) | 160.0s | 150.0s | **10.0s** | DPBPS $15\times$ faster detection |
| **E03 Spike: Time to 1st Scale-Up** | $\infty$ (Never) | 80.0s | 70.0s | **50.0s** | DPBPS detects pre-peak ramp |
| **E04 Sustained: Time to 1st Scale-Up** | $\infty$ (Never) | 40.0s | 50.0s | **30.0s** | Rapid saturation recognition |
| **E06 Bursty: Time to 1st Scale-Up** | $\infty$ (Never) | 50.0s | 40.0s | **20.0s** | Rapid burst detection |
| **E05 Decrease: Scale-Down Generated**| 0 | **1 (Erroneous)** | 0 (Stabilized) | **0 (Floor respected)**| CPU-Threshold fails floor guard |
| **E06 Bursty: Scale-Down Flapping** | 0 | **2 (Flapped)** | 0 (Stabilized) | **0 (Anti-flapped)** | DPBPS avoids lull thrashing |
| **Recommendation Reversals** | 0 | **2 reversals** | 0 | **0** | Zero churn in DPBPS |
| **Max Proposed Replicas** | 1 | 10 | 10 (Ceiling) | **4 – 8 (Bounded)** | Prevents resource runaway |

---

## 3. Bottleneck Prioritization & Dependency Awareness Analysis

### 3.1 Service Allocation Breakdown
The table below illustrates which microservices received SCALE_UP recommendations from each policy across the entire 1,050-evaluation campaign:

| Microservice | Call Graph Role | Observed P95 Latency | Observed CPU Ratio | CPU-Threshold Scale-Ups | HPA-Style Scale-Ups | Proposed DPBPS Scale-Ups |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`frontend`** | Ingress Proxy (Root) | **208 – 4,171 ms** (Saturated) | **0.80 – 1.69** | 13 (48.1%) | 21 (61.8%) | **23 (85.2%)** |
| **`checkoutservice`**| Core Orchestrator | 24 – 85 ms | 0.45 – 0.65 | 0 (0.0%) | 0 (0.0%) | **3 (11.1%)** |
| **`recommendationservice`**| Async ML Compute | 15 – 35 ms | 0.50 – 0.68 | 0 (0.0%) | 0 (0.0%) | **1 (3.7%)** |
| **`productcatalogservice`**| Read Leaf Node | **< 5.0 ms** (Uncongested) | 0.70 – 0.85* | **7 (25.9%)** | **7 (20.6%)** | 0 (0.0%) |
| **`currencyservice`** | In-Memory Leaf Node | **< 3.0 ms** (Uncongested) | 0.70 – 0.82* | **7 (25.9%)** | **6 (17.6%)** | 0 (0.0%) |
| **Remaining 5 Services**| Leaf / Backend Workers | < 5.0 ms | < 0.40 | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **Total Scale-Ups** | — | — | — | **27** | **34** | **27** |

*\*Note: `productcatalogservice` and `currencyservice` have tiny default CPU requests (50m–100m). Under high traffic, their utilization percentage exceeded 70%, but their absolute latency remained under 5 ms with zero queuing.*

```
Service Scaling Specificity Comparison:
DPBPS:         [==================== FRONTEND: 85.2% ====================] [== CHECKOUT: 11.1% ==] [= REC: 3.7% =]
HPA_STYLE:     [============== FRONTEND: 61.8% ==============] [=== CATALOG: 20.6% ===] [=== CURRENCY: 17.6% ===]
CPU_THRESHOLD: [=========== FRONTEND: 48.1% ===========] [===== CATALOG: 25.9% =====] [===== CURRENCY: 25.9% =====]
```

### 3.2 Analytical Insights
1. **The Fallacy of Single-Metric CPU Scaling:** Both CPU-Threshold and HPA-Style treat every microservice as an isolated pod. In microservice architectures, leaf services often run lightweight in-memory logic with low resource requests. When user concurrency rises, `currencyservice` and `productcatalogservice` easily reach 75% CPU utilization. Conventional CPU autoscalers immediately trigger scale-ups for these services, wasting cluster quota on nodes that are not degrading user experience.
2. **DPBPS Graph-Informed Prioritization:** DPBPS incorporates dependency graph centrality and P95 latency ratios into its pressure index. Because `productcatalogservice` maintained P95 latencies < 5 ms, its latency pressure term remained near zero, suppressing unnecessary scale-ups. Instead, DPBPS concentrated 96.3% of its scaling actions on `frontend` and `checkoutservice`, addressing the actual choke points of the application.

---

## 4. Resource Allocation Efficiency and Boundedness

### 4.1 Over-Provisioning Vulnerability in HPA-Style Policy
- The classic HPA formula $\lceil \text{current} \times (\text{util} / \text{target}) \rceil$ compounds rapidly when unactuated or when pods encounter sudden surges:
  - If a single pod operates at 140% CPU utilization, HPA immediately calculates $\lceil 1 \times (1.40 / 0.70) \rceil = 2$.
  - In the subsequent cycle, if CPU remains elevated, HPA compounds to $\lceil 2 \times (1.40 / 0.70) \rceil = 4$, and then $\min(10, 4 \times 2) = 8$, reaching the 10-replica ceiling within 30–40 seconds.
  - In a live deployment, this causes massive pod scheduling churn, cluster node scale-outs, and memory over-commitment.

### 4.2 DPBPS Bounded Scaling Stability
- DPBPS strictly enforces an incremental single-step scale-up policy (+1 replica per scaling event).
- In Experiment E03 (Sudden Spike of 80 users), while HPA surged to 10 replicas, DPBPS expanded to 5 replicas. Once the spike subsided at $t=90\text{s}$, DPBPS returned to HOLD, maintaining resource stability without unnecessary over-allocation.
- In Experiment E05 (Traffic Decrease), DPBPS recognized that all services were already operating at `current_replicas = 1`. In strict conformance with `min_replicas = 1`, it generated **100% HOLD decisions**, avoiding the illegal scale-down recommendation produced by the CPU-Threshold policy.

---

## 5. Comparative Evaluation Synthesis

| Dimension | Static Policy | CPU-Threshold Policy | HPA-Style Policy | Proposed DPBPS |
| :--- | :---: | :---: | :---: | :---: |
| **Response to Gradual Load** | Poor (No scaling) | Poor (Delayed by 150s) | Moderate (Compounding) | **Optimal (Early detection)** |
| **Response to Sudden Spikes** | Poor (No scaling) | Moderate | Aggressive (Over-provisions) | **Optimal (Bounded +1)** |
| **Anti-Flapping (Bursty)** | Optimal (Fixed) | Poor (Flaps during lulls) | Moderate (Stabilized) | **Optimal (Suppressed)** |
| **Floor Protection (< min)** | Optimal (Fixed) | Poor (Proposes scale-down)| Moderate | **Optimal (100% floor hold)** |
| **Bottleneck Attribution** | None | Poor (48% misdirected) | Moderate (38% misdirected)| **Optimal (96.3% bottleneck targeted)** |
| **CI/CD Lifecycle Awareness** | None | None | None | **Integrated (Phase aware)** |

---

## 6. Conclusion

The comparative performance analysis confirms that DPBPS outperforms conventional CPU-threshold and HPA-style reactive scalers across all core operational dimensions:
1. It eliminates the 150-second detection lag of pure CPU watermark scalers.
2. It prevents the rapid runaway over-provisioning characteristic of unconstrained proportional ratio scalers.
3. It completely suppresses scale-down flapping during oscillatory burst traffic.
4. It accurately targets microservice call graph bottlenecks, preventing wasted cluster capacity on uncongested leaf services.

