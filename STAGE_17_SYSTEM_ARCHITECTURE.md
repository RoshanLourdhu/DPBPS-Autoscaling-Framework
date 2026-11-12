# STAGE 17 — SYSTEM ARCHITECTURE SPECIFICATION
# DPBPS AUTOSCALING FRAMEWORK

**Project Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Algorithm:** DPBPS (Deployment-Phase-Aware Bottleneck-Prioritized Scaling)  
**Target Environment:** Google Online Boutique (10 Microservices) on Kubernetes  
**Document Version:** 1.0.0 (Production / Acceptance Release)  
**Date:** November 11, 2026  

---

## 1. HIGH-LEVEL SYSTEM TOPOLOGY

The DPBPS platform is a closed-loop, multi-dimensional autonomic autoscaler specifically engineered for microservice architectures subject to continuous integration and continuous deployment (CI/CD) rollouts.

```mermaid
flowchart TD
    subgraph Observability ["Observability & Telemetry Tier"]
        PROM["Prometheus Server\n(Scrape: 15s, App Metrics)"]
        K8S_MS["Kubernetes Metrics Server\n(Pod CPU & RAM Usage)"]
        K8S_API["Kubernetes AppsV1 API\n(Deployment Replicas & Specs)"]
    end

    subgraph StateTier ["State & Context Tier"]
        CICD["CI/CD Pipeline / Webhook\n(HMAC SHA-256 Validated)"]
        DSM["DeploymentStateManager\n(Per-Service Rollout Lifecycle)"]
        CICD -->|Rollout Events| DSM
    end

    subgraph ControllerCore ["DPBPS Closed-Loop Controller Tier"]
        ADAPTER["KubernetesTelemetryAdapter\n(Normalization & Validation)"]
        BNDETECT["BottleneckPrioritizationEngine\n(Dependency Graph Analysis)"]
        CTRL["ContinuousDPBPSController\n(15s Evaluation Cycle)"]
        
        PROM -->|App Telemetry| ADAPTER
        K8S_MS -->|Node/Pod Top| ADAPTER
        K8S_API -->|Replica Baseline| ADAPTER
        
        ADAPTER -->|Validated TelemetryInput| CTRL
        DSM -->|Deployment Phase & Guardrails| CTRL
        CTRL -->|Dependency Tracing| BNDETECT
        BNDETECT -->|Bottleneck Service Flag| CTRL
    end

    subgraph ActuatorTier ["Execution & Safety Actuator Tier"]
        ACT["HardenedKubernetesActuator\n(Fail-Closed, Dry-Run / Live)"]
        ESTOP["Emergency Stop Guard\n(Instant Zero-Lag Interception)"]
        ROLLBACK["Automated Rollback Engine\n(Post-Action Readiness Check)"]
        
        CTRL -->|DecisionOutput| ACT
        ESTOP -.->|Safety Intercept| ACT
        ACT -->|Verify Readiness| ROLLBACK
        ROLLBACK -.->|Revert Replicas| ACT
    end

    subgraph TargetCluster ["Google Online Boutique (online-boutique)"]
        FE["frontend (Go)"]
        CS["cartservice (C#)"]
        PC["productcatalogservice (Go)"]
        CK["checkoutservice (Go)"]
        CU["currencyservice (Node.js)"]
        PM["paymentservice (Node.js)"]
        SH["shippingservice (Go)"]
        EM["emailservice (Python)"]
        RS["recommendationservice (Python)"]
        AD["adservice (Java)"]
        RC[("redis-cart (PROTECTED)")]
        OTEL["opentelemetrycollector (PROTECTED)"]
        
        ACT ==>|Scale Patch (Scale Subresource)| PC
        ACT -.->|Allowlist Controlled| FE
        ACT -.->|Allowlist Controlled| CS
        ACT -.->|Allowlist Controlled| CK
    end

    subgraph PresentationTier ["DPBPS Management Dashboard (React 18 + Vite)"]
        UI_OVERVIEW["Overview Dashboard (/)"]
        UI_SERVICES["Service Health (/services)"]
        UI_TOPOLOGY["Topology Map (/topology)"]
        UI_BOTTLENECK["Bottleneck Analysis (/bottlenecks)"]
        UI_INTELLIGENCE["DPBPS Intelligence (/intelligence)"]
        UI_SCALING["Scaling Operations (/scaling)"]
        UI_HISTORY["Scaling History (/scaling-history)"]
        UI_DEPLOYMENTS["CI/CD Deployments (/deployments)"]
        UI_ANALYTICS["Performance Analytics (/analytics)"]
        UI_EXPERIMENTS["Experiments & Evaluation (/experiments)"]
    end
```

---

## 2. COMPONENT ARCHITECTURAL DESCRIPTIONS

### 2.1 Observability and Telemetry Adapter (`backend/scaling/kubernetes/telemetry_adapter.py`)
- **Ingestion Sources:** Combines application-level traffic (request rate, $P_{95}$ latency, error rate) from Prometheus with container-level resource utilization (CPU millicores, working set memory) from Kubernetes Metrics Server.
- **Normalization:** Formulates normalized utilization ratios relative to container resource requests:
  $$U_{\text{CPU}} = \frac{\text{CPU Usage (mCPU)}}{\text{CPU Request (mCPU)}}, \quad U_{\text{Memory}} = \frac{\text{Memory Usage (MiB)}}{\text{Memory Request (MiB)}}$$
- **Data Completeness & Freshness:** Requires sample age $\le 30\text{ seconds}$. Services with missing or stale streams are explicitly isolated into an `excluded` diagnostic partition rather than synthesized with zero values.

### 2.2 CI/CD Deployment State Manager (`backend/scaling/deployment_state.py`)
- **Lifecycle Phases:** Tracks per-service lifecycle transitions:
  - `PRE_DEPLOYMENT`: Pre-warming phase. Scale-down operations are strictly suppressed.
  - `ACTIVE_DEPLOYMENT`: Pod rollout in progress. Scale-down operations are prohibited to prevent premature pod eviction during startup cold-start.
  - `POST_DEPLOYMENT`: Stabilization window (60s). Scale-down is delayed until post-rollout performance stabilizes.
  - `NORMAL_OPERATION`: Standard steady-state elastic scaling.
- **Durable Persistence:** Rollout history and cooldown timestamps are persisted atomically to `backend/data/deployment_state.json`.

### 2.3 Continuous DPBPS Controller (`backend/scaling/continuous_controller.py`)
- **Asynchronous Execution:** Runs on a non-overlapping asynchronous loop (`asyncio.Lock`) every 15 seconds.
- **Bottleneck Prioritization:** Employs the canonical Online Boutique dependency call-graph to identify the critical-path bottleneck service. Downstream bottlenecks prioritize scaling of the root leaf/worker service while holding upstream callers to prevent backpressure amplification.
- **Decision Multi-Dimensional Weighting:** Evaluates composite service pressure:
  $$P_{\text{agg}} = w_{\text{cpu}} P_{\text{cpu}} + w_{\text{mem}} P_{\text{mem}} + w_{\text{lat}} P_{\text{lat}} + w_{\text{err}} P_{\text{err}}$$
  Default weights: $w_{\text{cpu}}=0.40, w_{\text{mem}}=0.20, w_{\text{lat}}=0.30, w_{\text{err}}=0.10$.

### 2.4 Hardened Kubernetes Scaling Actuator (`backend/scaling/kubernetes/actuator.py`)
- **Mutation Boundary:** Executes replica changes exclusively via the Kubernetes `patch_namespaced_deployment_scale` subresource API.
- **Guardrails:**
  - Strict replica boundaries: $[R_{min}, R_{max}] = [1, 3]$.
  - Step clamping: $|\Delta R| \le 1$ per cycle.
  - Cooldown timers: 60-second anti-flapping window.
  - Optimistic concurrency: Live desired replicas must match decision baseline.
- **Post-Action Verification & Automated Rollback:** Actively polls pod readiness up to 60 seconds. In the event of readiness probe failure or rollout progress deadline expiration, the automated rollback engine immediately reverts the deployment to its baseline replica count.

### 2.5 Frontend Application Shell & Dashboard (`frontend/src/`)
- **Technology Stack:** React 18, TypeScript 5, Vite 8, Tailwind CSS, Lucide React icons.
- **Real-Time Responsiveness:** Employs React Query polling (5s interval) and WebSocket/SSE streaming hooks to reflect cluster health, scaling decisions, active deployment rollouts, and Prometheus metrics with zero latency.
- **Ten Dedicated Workspaces:**
  1. `/`: Overview dashboard with system health KPI cards and activity timeline.
  2. `/services`: Real-time microservices table with CPU, RAM, and latency bars.
  3. `/topology`: Interactive SVG service call-graph topology map.
  4. `/bottlenecks`: Critical-path bottleneck radar and service pressure breakdown.
  5. `/intelligence`: Real-time DPBPS decision explainability and pressure weights.
  6. `/scaling`: Live actuator controls, allowlist configuration, and Emergency Stop.
  7. `/scaling-history`: Paginated audit log of all validated and applied scaling actions.
  8. `/deployments`: CI/CD rollout phase status and active deployment timeline.
  9. `/analytics`: Comparative latency distributions, throughput graphs, and resource costs.
  10. `/experiments`: Benchmark results across all 8 experimental scenarios.

