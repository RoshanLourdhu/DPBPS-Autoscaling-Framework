# STAGE 9.2 — BASELINE SCALING POLICY METHODOLOGY

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Author:** Roshan Lourdhu  
**Date:** 2026-11-10  
**Phase:** 9.2 Comparative Evaluation Methodology & Baseline Policy Architecture  

---

## 1. Executive Summary

This document specifies the architectural design, algorithmic models, mathematical formulations, and evaluation assumptions for the four autoscaling policies evaluated in Stage 9:
1. **Baseline A — Static Resource Allocation:** Reference baseline with constant replica allocation.
2. **Baseline B — CPU-Threshold Reactive Scaling:** Dual-watermark static threshold controller with cooldown and sustained noise filtering.
3. **Baseline C — Conventional Reactive HPA-Style Policy:** Kubernetes Horizontal Pod Autoscaler proportional ratio approximation with stabilization windows.
4. **Proposed Approach — DPBPS:** Deployment-phase-aware, bottleneck-prioritized, dependency-graph-informed dynamic scaling.

All policies are evaluated in an offline, trace-replay evaluation module (`backend/evaluation/`) completely isolated from live Kubernetes actuators. Each policy receives identical time-series telemetry observations from Experiments E01–E06, ensuring rigorous, reproducible comparative evaluation without experimental bias.

---

## 2. Policy Specifications and Mathematical Formulations

```
Autoscaling Policy Taxonomy:
+-----------------------------------------------------------------------------+
|                      Comparative Autoscaling Policies                        |
+------------------------------------+----------------------------------------+
|  Conventional Baseline Policies    |  Proposed DPBPS Architecture           |
|  - Static Allocation (Fixed)       |  - Deployment Phase Aware              |
|  - CPU-Threshold (Dual Watermark)  |  - Bottleneck Prioritized              |
|  - HPA-Style (Proportional Ratio)  |  - Multi-Dimensional (Latency+CPU+Dep) |
+------------------------------------+----------------------------------------+
```

### 2.1 Baseline A — Static Resource Allocation
- **Characteristics:** Fixed capacity; zero dynamic adjustments in response to traffic or resource fluctuations.
- **Mathematical Model:**
  $$R_t = R_0 = 1 \quad \forall t \ge 0$$
  $$\Delta R_t = 0, \quad \text{Action}_t = \text{HOLD}$$
- **Role in Evaluation:** Serves as the experimental control baseline representing an unscaled microservice deployment. It provides the reference performance boundary against which dynamic autoscaling responsiveness and resource efficiency are measured.

---

### 2.2 Baseline B — Conventional CPU-Threshold Reactive Scaling
- **Characteristics:** Threshold-based watermark controller typical of cloud monitoring auto-scalers (e.g., AWS Auto Scaling dynamic target tracking, Prometheus Alertmanager webhook scaling).
- **Mathematical Model:**
  $$\text{Action}_t = \begin{cases}
  \text{SCALE\_UP}, & \text{if } U_{CPU}(t) > \theta_{high} \text{ for } k \ge 2 \text{ cycles and } (t - t_{last}) \ge \tau_{cd} \\
  \text{SCALE\_DOWN}, & \text{if } U_{CPU}(t) < \theta_{low} \text{ for } k \ge 2 \text{ cycles and } (t - t_{last}) \ge \tau_{cd} \\
  \text{HOLD}, & \text{otherwise}
  \end{cases}$$
- **Evaluation Parameters:**
  - Scale-Up Watermark ($\theta_{high}$): **70% (0.70)** CPU utilization ratio.
  - Scale-Down Watermark ($\theta_{low}$): **30% (0.30)** CPU utilization ratio.
  - Minimum Replicas ($R_{min}$): **1**.
  - Maximum Replicas ($R_{max}$): **10**.
  - Maximum Step Change ($\Delta R_{max}$): **2 replicas** (proportional to overload severity).
  - Cooldown Window ($\tau_{cd}$): **30.0 seconds** (3 evaluation cycles).
  - Sustained Threshold Constraint ($k$): **2 consecutive evaluation cycles** required to filter transient metric noise.
- **Limitations:** Only observes CPU utilization; blind to ingress HTTP queue depths, downstream gRPC latencies, and service dependency chains.

---

### 2.3 Baseline C — Conventional Kubernetes HPA-Style Reactive Policy
- **Characteristics:** Proportional ratio autoscaling modeled after the upstream Kubernetes Horizontal Pod Autoscaler algorithm (`autoscaling/v2`).
- **Mathematical Formulation:**
  $$\text{ratio}_t = \frac{U_{CPU}(t)}{U_{target}}$$
  $$\text{desiredReplicas}_t = \left\lceil R_{current} \times \text{ratio}_t \right\rceil$$
- **Tolerance Band:**
  $$\text{If } |1.0 - \text{ratio}_t| \le \epsilon \implies \text{Action}_t = \text{HOLD} \quad (\epsilon = 0.10)$$
- **Scale-Down Stabilization Window:**
  - To prevent oscillation, scale-down proposals are retained in a rolling historical window of duration $\tau_{down} = 60.0\text{ seconds}$.
  - The controller selects the **maximum desired replica count** within the stabilization window before executing a downscale:
    $$R_{stabilized} = \max_{t' \in [t - \tau_{down}, t]} \{ \text{desiredReplicas}_{t'} \}$$
- **Scale-Up Constraints:**
  - Scale-up takes immediate effect ($\tau_{up} = 0\text{s}$) to safeguard SLAs.
  - Maximum scale-up rate: $\min(R_{max}, \max(2 \times R_{current}, R_{current} + 4))$.
- **Evaluation Parameters:**
  - Target CPU Utilization ($U_{target}$): **70% (0.70)**.
  - Tolerance ($\epsilon$): **10%** (operational band $[63\%, 77\%]$).
  - Bounds: $R_{min} = 1, R_{max} = 10$.
- **Limitations:** Evaluates individual microservices in isolation without dependency topology or deployment lifecycle context.

---

### 2.4 Proposed Approach — DPBPS
- **Characteristics:** Multi-dimensional, deployment-phase-aware, bottleneck-prioritized scaling controller.
- **Key Algorithmic Pillars:**
  1. **Deployment Phase Awareness:** Modulates scaling aggression and cooldown based on CI/CD deployment phase:
     - `PRE_DEPLOYMENT`: Proactive warm-up headroom.
     - `ACTIVE_DEPLOYMENT`: Conservative scale-down suppression; rapid canary scaling.
     - `POST_DEPLOYMENT`: Controlled stabilization.
     - `NORMAL_OPERATION`: Production steady-state tracking.
  2. **Multi-Dimensional Pressure Index ($P_i$):**
     $$P_i = w_{cpu} \cdot U_{CPU} + w_{mem} \cdot U_{mem} + w_{lat} \cdot \left(\frac{L_{P95}}{L_{target}}\right) + w_{err} \cdot E_{rate}$$
     where weights are $w_{cpu} = 0.4, w_{mem} = 0.2, w_{lat} = 0.3, w_{err} = 0.1$, and $L_{target} = 200\text{ ms}$.
  3. **Bottleneck Prioritization:**
     - Evaluates the directed dependency graph $G = (V, E)$.
     - Identifies the service with the highest combined pressure and graph centrality.
     - Issues bounded scale-up (+1) strictly to bottleneck nodes to prevent upstream starvation and downstream queue explosion.
  4. **Anti-Flapping & Floor Protection:**
     - Enforces single-step scaling increments.
     - Strictly enforces $R \ge R_{min} = 1$, preventing destructive downscale proposals below baseline capacity.

---

## 3. Evaluation Schema & Normalization

All policies receive identical `NormalizedObservation` records generated by `backend/evaluation/trace_loader.py`:

```json
{
  "experiment_id": "exp_20261110T165351_gradual_traffic_increase_309b2d79",
  "service_name": "frontend",
  "timestamp": "2026-11-10T16:54:33.172849+00:00",
  "elapsed_seconds": 40.0,
  "stage": "Stage 1 (10u)",
  "request_rate": 4.90,
  "p50_latency_ms": 22.50,
  "p95_latency_ms": 3991.00,
  "p99_latency_ms": 4850.00,
  "error_rate": 0.00,
  "cpu_usage_millicores": 45.20,
  "memory_usage_mib": 12.80,
  "cpu_utilization_ratio": 0.452,
  "memory_utilization_ratio": 0.200,
  "current_replicas": 1,
  "telemetry_available": true,
  "deployment_phase": "NORMAL_OPERATION"
}
```

### Telemetry Quality Rules
1. **Unpopulated Telemetry:** When `telemetry_available = false`, all dynamic policies output `INSUFFICIENT_DATA` / `HOLD` with zero replica changes. No policy is permitted to fabricate synthetic metric values.
2. **Synchronous Time Step:** Replay engine evaluates all 10 microservices per snapshot simultaneously, ensuring identical chronological ordering across all policies.

---

## 4. Evaluation Constraints & Non-Live Scaling Notice

> [!IMPORTANT]
> **Trace-Replay Operational Constraint:**
> During Experiments E01–E06, the Kubernetes scaling actuator operated strictly in `DRY_RUN` mode. Consequently, the empirical telemetry recorded during these runs reflects the behavior of an unscaled single-pod cluster.
> 
> In this offline evaluation, all four policies evaluate identical historical telemetry traces. When a policy recommends a scale-up (e.g., target 2 replicas), that recommendation is recorded in the policy's simulated state, but **no real pod was created in the recorded trace**.
> 
> Therefore, this evaluation measures **decision quality, responsiveness, stability, and bottleneck attribution**, and does not claim measured production latency reduction or resource savings.

