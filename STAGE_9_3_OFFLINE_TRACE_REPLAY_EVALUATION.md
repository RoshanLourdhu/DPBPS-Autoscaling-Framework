# STAGE 9.3 — OFFLINE TRACE-REPLAY EVALUATION

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Author:** Roshan Lourdhu  
**Date:** 2026-11-10  
**Phase:** 9.3 Trace-Replay Execution, Telemetry Serialization & Policy Decision Audit  

---

## 1. Executive Summary

This document presents the empirical execution logs and data synthesis of the offline trace-replay evaluation conducted across all six benchmark experiments:
- **E01:** `NORMAL_TRAFFIC` (`exp_20261110T152425_normal_traffic_838109a5`)
- **E02:** `GRADUAL_TRAFFIC_INCREASE` (`exp_20261110T165351_gradual_traffic_increase_309b2d79`)
- **E03:** `SUDDEN_TRAFFIC_SPIKE` (`exp_20261110T170244_sudden_traffic_spike_d80c4694`)
- **E04:** `SUSTAINED_HIGH_TRAFFIC` (`exp_20261110T172135_sustained_high_traffic_51ce3165`)
- **E05:** `TRAFFIC_DECREASE` (`exp_20261110T172806_traffic_decrease_71144bfe`)
- **E06:** `BURSTY_TRAFFIC` (`exp_20261110T173312_bursty_traffic_55733a14`)

A total of **1,050 microservice telemetry observations** spanning **105 discrete time snapshots** across all 10 Online Boutique services were replayed synchronously through Static Allocation, CPU-Threshold Scaling, HPA-Style Scaling, and DPBPS.

---

## 2. Comprehensive Trace-Replay Results by Experiment

### 2.1 Master Results Matrix Across Policies and Workloads
| Experiment Profile | Evaluation Dimension | Static Policy | CPU-Threshold Policy | HPA-Style Policy | Proposed DPBPS |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **E01: Normal Traffic** | Total Evaluations | 140 | 140 | 140 | 140 |
| (10 users, 140s) | HOLD Decisions | **140 (100.0%)** | 108 (77.1%) | 108 (77.1%) | 107 (76.4%) |
| | Scale-Up Decisions | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 1 (0.7%) |
| | Scale-Down Decisions | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| | Time to 1st Scale-Up | N/A | N/A | N/A | 40.0s |
| | Max Recommended Replicas | 1 | 1 | 1 | 2 |
| | Decision Stability | **100.0%** | 77.1%* | 77.1%* | 76.4%* |
| **E02: Gradual Increase** | Total Evaluations | 190 | 190 | 190 | 190 |
| (10 $\to$ 25 $\to$ 50u, 190s) | HOLD Decisions | 190 (100.0%) | 189 (99.5%) | 186 (97.9%) | 183 (96.3%) |
| | Scale-Up Decisions | 0 (0.0%) | 1 (0.5%) | 4 (2.1%) | **7 (3.7%)** |
| | Scale-Down Decisions | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| | Time to 1st Scale-Up | N/A | 160.0s (Lagged) | 150.0s (Lagged) | **10.0s (Responsive)** |
| | Max Recommended Replicas | 1 | 3 | 10 (Max cap) | 4 (Bounded) |
| | Decision Stability | 100.0% | 99.5% | 97.9% | 96.3% |
| **E03: Sudden Spike** | Total Evaluations | 130 | 130 | 130 | 130 |
| (5 $\to$ 80 $\to$ 5u, 130s) | HOLD Decisions | 130 (100.0%) | 125 (96.2%) | 120 (92.3%) | 126 (96.9%) |
| | Scale-Up Decisions | 0 (0.0%) | 5 (3.8%) | 10 (7.7%) | 4 (3.1%) |
| | Scale-Down Decisions | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| | Time to 1st Scale-Up | N/A | 80.0s | 70.0s | **50.0s** |
| | Max Recommended Replicas | 1 | 5 | 10 (Max cap) | 5 (Bounded) |
| | Decision Stability | 100.0% | 96.2% | 92.3% | 96.9% |
| **E04: Sustained High** | Total Evaluations | 230 | 230 | 230 | 230 |
| (60u plateau, 230s) | HOLD Decisions | 230 (100.0%) | 216 (93.9%) | 221 (96.1%) | 223 (97.0%) |
| | Scale-Up Decisions | 0 (0.0%) | 14 (6.1%) | 9 (3.9%) | 7 (3.0%) |
| | Scale-Down Decisions | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| | Time to 1st Scale-Up | N/A | 40.0s | 50.0s | **30.0s** |
| | Max Recommended Replicas | 1 | 10 (Max cap) | 10 (Max cap) | 8 (Gradual) |
| | Decision Stability | 100.0% | 93.9% | 96.1% | 97.0% |
| **E05: Traffic Decrease** | Total Evaluations | 190 | 190 | 190 | 190 |
| (50 $\to$ 25 $\to$ 5u, 190s) | HOLD Decisions | 190 (100.0%) | 187 (98.4%) | 186 (97.9%) | **190 (100.0%)** |
| | Scale-Up Decisions | 0 (0.0%) | 2 (1.1%) | 4 (2.1%) | 0 (0.0%) |
| | Scale-Down Decisions | 0 (0.0%) | **1 (0.5%)** | 0 (0.0%) | **0 (0.0%)** |
| | Time to 1st Scale-Up | N/A | 40.0s | 30.0s | N/A |
| | Max Recommended Replicas | 1 | 5 | 10 (Max cap) | 1 |
| | Decision Stability | 100.0% | 98.4% | 97.9% | **100.0%** |
| **E06: Bursty Traffic** | Total Evaluations | 170 | 170 | 170 | 170 |
| (4 cycles: 60u/5u, 170s) | HOLD Decisions | 170 (100.0%) | 163 (95.9%) | 163 (95.9%) | 162 (95.3%) |
| | Scale-Up Decisions | 0 (0.0%) | 5 (2.9%) | 7 (4.1%) | 8 (4.7%) |
| | Scale-Down Decisions | 0 (0.0%) | **2 (1.2%)** | 0 (0.0%) | **0 (0.0%)** |
| | Time to 1st Scale-Up | N/A | 50.0s | 40.0s | **20.0s** |
| | Max Recommended Replicas | 1 | 4 | 10 (Max cap) | 9 |
| | Decision Stability | 100.0% | 95.9% | 95.9% | 95.3% |
| **CAMPAIGN TOTALS** | **Total Evaluations** | **1,050** | **1,050** | **1,050** | **1,050** |
| (All 6 Profiles) | **Total HOLD Decisions** | **1,050 (100%)** | **988 (94.1%)** | **984 (93.7%)** | **991 (94.4%)** |
| | **Total Scale-Up Dec.** | **0 (0.0%)** | **27 (2.6%)** | **34 (3.2%)** | **27 (2.6%)** |
| | **Total Scale-Down Dec.**| **0 (0.0%)** | **3 (0.3%)** | **0 (0.0%)** | **0 (0.0%)** |
| | **Overall Stability** | **100.0%** | **94.1%** | **93.7%** | **94.4%** |

*\*Note: In E01, 32 observations (snaps 0–5) had empty Prometheus rate vectors due to downstream services receiving zero traffic during landing-page warmup. These were classified as `INSUFFICIENT_DATA` / `HOLD` without scaling.*

---

## 3. Key Operational Findings from Trace Replay

### 3.1 Responsiveness to Expanding Demand (E02 Gradual Increase)
- **CPU-Threshold Latency:** Under a gradual increase from 10 to 25 to 50 users, CPU-Threshold did not issue its first scale-up until **$t=160.0\text{s}$**, because `frontend` CPU utilization hovered around 50–65% during Stages 1 and 2, only breaching 70% late in Stage 3.
- **HPA-Style Latency:** HPA-Style issued its first scale-up at **$t=150.0\text{s}$**, but once triggered, compounded desired replicas directly up to the **10 replica maximum ceiling**.
- **DPBPS Responsiveness:** DPBPS issued its first scale-up recommendation at **$t=10.0\text{s}$** and another at $t=20\text{s}$. Because DPBPS observes multi-dimensional metrics (request rate surge and P95 latency inflation alongside CPU), it detected capacity pressure long before raw CPU exceeded the static 70% threshold.

### 3.2 Anti-Flapping Resilience Under Bursty Oscillations (E06)
- In Experiment E06, virtual users alternated rapidly between 60 users and 5 users every 20 seconds.
- **CPU-Threshold Flapping:** CPU-Threshold issued **2 scale-down recommendations** during the 20-second lull intervals. Because CPU utilization dropped below 30% during the lull, the controller attempted to downscale, only to be hit 20 seconds later by another 60-user burst, demonstrating the classic thrashing failure mode of simple watermark scalers.
- **DPBPS Anti-Flapping:** DPBPS generated **0 scale-down recommendations** throughout all four burst cycles. The algorithm recognized that the 20-second lull was within the transient cooldown and stabilization window, preventing destructive pod termination.

### 3.3 Over-Provisioning vs Bounded Increments (E03 & E04)
- Under severe load spikes (E03: 80 users) and sustained plateaus (E04: 60 users), HPA-Style proportional scaling computed ratios of $1.5\times - 2.5\times$, repeatedly expanding capacity to the **10 replica ceiling**.
- DPBPS maintained strict **single-step increments (+1 replica per scaling event)**. In E03, it proposed a max of 5 replicas; in E04, it gradually expanded to 8 replicas across the 180s plateau, effectively preventing panic over-provisioning.

---

## 4. Replay Fidelity & Reproducibility Certification

- Replay execution was validated for 100% determinism: re-running the engine on the identical trace outputs identical recommendations, replica counts, and timestamps.
- Zero external network requests or live Kubernetes API calls were performed during this evaluation.
- All empirical inputs and outputs are preserved in structured memory for downstream statistical synthesis.

