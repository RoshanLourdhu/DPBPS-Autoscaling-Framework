# STAGE 17 — DPBPS ALGORITHM DESIGN AND MATHEMATICAL FORMULATION
# FORMAL SPECIFICATION OF DEPLOYMENT-PHASE-AWARE BOTTLENECK-PRIORITIZED SCALING

**Project Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Algorithm Name:** DPBPS (Deployment-Phase-Aware Bottleneck-Prioritized Scaling)  
**Document Version:** 1.0.0 (Formal Research Specification)  
**Date:** November 11, 2026  

---

## 1. MATHEMATICAL FORMULATION OF SYSTEM STATE

Let the microservice system be represented as a directed acyclic graph (DAG) $\mathcal{G} = (\mathcal{V}, \mathcal{E})$, where:
- $\mathcal{V} = \{s_1, s_2, \dots, s_M\}$ is the set of $M$ microservices.
- $\mathcal{E} \subseteq \mathcal{V} \times \mathcal{V}$ is the set of directed RPC invocation edges. An edge $(s_i, s_j) \in \mathcal{E}$ indicates that upstream service $s_i$ invokes downstream service $s_j$.
- $\mathcal{D}(s_i) = \{s_j \in \mathcal{V} \mid (s_i, s_j) \in \mathcal{E}\}$ represents the immediate downstream dependencies of $s_i$.

At any discrete evaluation cycle $t \in \mathbb{N}$ with observation interval $\Delta t = 15\text{ s}$, each service $s \in \mathcal{V}$ is characterized by the telemetry observation tuple:
$$\mathbf{x}_s(t) = \langle U_{\text{cpu},s}(t), U_{\text{mem},s}(t), L_{95,s}(t), E_s(t), R_s(t), \Phi_s(t) \rangle$$
where:
- $U_{\text{cpu},s}(t) \in [0, \infty)$ is the normalized CPU utilization ratio relative to configured requests.
- $U_{\text{mem},s}(t) \in [0, 1]$ is the memory working set utilization ratio relative to configured requests.
- $L_{95,s}(t) \in [0, \infty)$ is the 95th percentile response latency in milliseconds.
- $E_s(t) \in [0, 1]$ is the fractional error rate (non-2xx HTTP or non-OK gRPC status codes).
- $R_s(t) \in \mathbb{N}_{\ge 1}$ is the current active replica allocation.
- $\Phi_s(t) \in \{\text{NORMAL}, \text{PRE\_DEPLOYMENT}, \text{ACTIVE\_DEPLOYMENT}, \text{POST\_DEPLOYMENT}\}$ is the active CI/CD deployment phase.

---

## 2. MULTI-DIMENSIONAL SERVICE PRESSURE FORMULATION

For each service $s \in \mathcal{V}$, individual pressure dimensions are normalized against target operating thresholds:

$$\begin{aligned}
P_{\text{cpu},s}(t) &= \max\left(0, \frac{U_{\text{cpu},s}(t) - \theta_{\text{cpu}}}{1 - \theta_{\text{cpu}}}\right) \\
P_{\text{mem},s}(t) &= \max\left(0, \frac{U_{\text{mem},s}(t) - \theta_{\text{mem}}}{1 - \theta_{\text{mem}}}\right) \\
P_{\text{lat},s}(t) &= \max\left(0, \frac{L_{95,s}(t) - \theta_{\text{lat}}}{\theta_{\text{lat}}}\right) \\
P_{\text{err},s}(t) &= \min(1.0, E_s(t))
\end{aligned}$$

The aggregate pressure metric $P_{\text{agg},s}(t)$ is formulated as a convex combination of the normalized components:
$$P_{\text{agg},s}(t) = w_{\text{cpu}} P_{\text{cpu},s}(t) + w_{\text{mem}} P_{\text{mem},s}(t) + w_{\text{lat}} P_{\text{lat},s}(t) + w_{\text{err}} P_{\text{err},s}(t)$$
subject to the simplex constraint:
$$w_{\text{cpu}} + w_{\text{mem}} + w_{\text{lat}} + w_{\text{err}} = 1.0, \quad w_i \ge 0$$
Canonical parameter weights:
$$w_{\text{cpu}} = 0.40, \quad w_{\text{mem}} = 0.20, \quad w_{\text{lat}} = 0.30, \quad w_{\text{err}} = 0.10$$
Default thresholds:
$$\theta_{\text{cpu}} = 0.75, \quad \theta_{\text{mem}} = 0.80, \quad \theta_{\text{lat}} = 150.0\text{ ms}$$

---

## 3. BOTTLENECK DETECTION AND PRIORITIZATION

Conventional autoscalers scale upstream and downstream services independently, frequently over-allocating upstream callers while the true root cause remains throttled downstream.

### 3.1 Bottleneck Identification
A service $s \in \mathcal{V}$ is defined as a candidate bottleneck if its latency or error rate violates service-level objectives:
$$\mathcal{C}(t) = \left\{ s \in \mathcal{V} \;\middle|\; L_{95,s}(t) > L_{\text{crit}} \;\lor\; E_s(t) > E_{\text{crit}} \right\}$$
where $L_{\text{crit}} = 500.0\text{ ms}$ and $E_{\text{crit}} = 0.05$ ($5\%$).

The primary bottleneck $s^*(t)$ is selected via lexicographical priority:
$$s^*(t) = \arg\max_{s \in \mathcal{C}(t)} \Big( L_{95,s}(t), E_s(t) \Big)$$
If $\mathcal{C}(t) = \emptyset$, then $s^*(t) = \text{None}$.

### 3.2 Prioritized Backpressure Modulation
When a bottleneck $s^*(t)$ is active:
1. **Bottleneck Prioritization:** The bottleneck service $s^*(t)$ receives scale-up priority ($\Delta R_{s^*} \ge 1$).
2. **Upstream Scale-Down / Scale-Up Suppression:** For all services $s \neq s^*(t)$ where $s^*(t)$ lies in the transitive downstream call path ($\exists \text{ path } s \rightsquigarrow s^*$), scaling is clamped to `HOLD`:
$$\Delta R_s(t) = 0, \quad \text{Action}_s(t) = \text{HOLD}$$
This prevents queue amplification and memory blowout in callers while the bottleneck is being resolved.

---

## 4. DEPLOYMENT-PHASE MODULATION RULES

Autoscaling decisions are dynamically modulated according to the active CI/CD lifecycle phase $\Phi_s(t)$:

```mermaid
stateDiagram-v2
    [*] --> NORMAL_OPERATION
    NORMAL_OPERATION --> PRE_DEPLOYMENT: CI/CD Webhook (Pre-warm)
    PRE_DEPLOYMENT --> ACTIVE_DEPLOYMENT: Pod Rollout Starts
    ACTIVE_DEPLOYMENT --> POST_DEPLOYMENT: Pods Ready, Traffic Shifts
    POST_DEPLOYMENT --> NORMAL_OPERATION: Stabilization Window Elapses (60s)
    
    note right of PRE_DEPLOYMENT: Scale-down prohibited
    note right of ACTIVE_DEPLOYMENT: Scale-down strictly blocked; Scale-up allowed
    note right of POST_DEPLOYMENT: Scale-down requires t - t_rollout >= 60s
```

### 4.1 Phase Transition Guardrails
Let $\Delta R_{\text{raw},s}(t)$ be the initial replica delta derived from $P_{\text{agg},s}(t)$:
$$\Delta R_{\text{raw},s}(t) = \begin{cases}
+1, & \text{if } P_{\text{agg},s}(t) > 0.20 \\
-1, & \text{if } P_{\text{agg},s}(t) < 0.05 \\
0, & \text{otherwise}
\end{cases}$$

The deployment-modulated delta $\Delta R_{\text{phase},s}(t)$ is defined as:
$$\Delta R_{\text{phase},s}(t) = \begin{cases}
0, & \text{if } \Phi_s(t) \in \{\text{PRE\_DEPLOYMENT}, \text{ACTIVE\_DEPLOYMENT}\} \land \Delta R_{\text{raw},s}(t) < 0 \\
0, & \text{if } \Phi_s(t) = \text{POST\_DEPLOYMENT} \land \Delta R_{\text{raw},s}(t) < 0 \land (t - t_{\text{rollout}}) < \tau_{\text{stab}} \\
\Delta R_{\text{raw},s}(t), & \text{otherwise}
\end{cases}$$
where $\tau_{\text{stab}} = 60\text{ seconds}$.

---

## 5. ACTUATOR HYSTERESIS AND SAFETY INVARIANTS

### 5.1 Bounded Replica Allocation
The final target replica count $R_{\text{target},s}(t)$ is strictly bounded:
$$R_{\text{target},s}(t) = \max\left( R_{\text{min}}, \min\left( R_{\text{max}}, R_s(t) + \operatorname{clamp}(\Delta R_{\text{phase},s}(t), -\Delta_{\text{max}}, +\Delta_{\text{max}}) \right) \right)$$
where $R_{\text{min}} = 1, R_{\text{max}} = 3, \Delta_{\text{max}} = 1$.

### 5.2 Anti-Flapping Cooldown Hysteresis
Let $t_{\text{last},s}$ be the timestamp of the last executed scaling action on service $s$. A new scaling decision is permitted if and only if:
$$(t - t_{\text{last},s}) \ge \tau_{\text{cooldown}} \quad (\tau_{\text{cooldown}} = 60\text{ s})$$
If $(t - t_{\text{last},s}) < \tau_{\text{cooldown}}$, the actuator enforces `REJECTED_COOLDOWN_ACTIVE`.

### 5.3 Mathematical Proof of System Invariants
- **Theorem 1 (Replica Safety):** $\forall t \ge 0, \forall s \in \mathcal{V}: R_s(t) \in [R_{\text{min}}, R_{\text{max}}]$.  
  *Proof:* Since $R_s(0) = 1 \in [1, 3]$ and $R_{\text{target}}$ is clamped by $\max(R_{\text{min}}, \min(R_{\text{max}}, \cdot))$, the replica count cannot leave the interval $[R_{\text{min}}, R_{\text{max}}]$.
- **Theorem 2 (Single-Step Elasticity):** $\forall t \ge 0, \forall s \in \mathcal{V}: |R_s(t) - R_s(t - \Delta t)| \le \Delta_{\text{max}} = 1$.  
  *Proof:* $\operatorname{clamp}(\Delta R, -1, +1)$ enforces that any individual change is at most $\pm 1$.
- **Theorem 3 (Anti-Oscillation Stability):** Between any two scaling actions on service $s$, there exists an unperturbed observation window of at least $\tau_{\text{cooldown}} = 60\text{ seconds}$.  
  *Proof:* The actuator verifies $(t - t_{\text{last},s}) \ge 60\text{s}$ before accepting any non-HOLD decision, guaranteeing an upper bound on scaling frequency of $f_{\text{scale}} \le 1\text{ action / } 60\text{ seconds}$.

