# STAGE 17 — API AND COMPONENT REFERENCE MANUAL
# COMPLETE TECHNICAL REFERENCE FOR DPBPS SYSTEM INTERFACES

**Project Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Framework:** DPBPS  
**Document Version:** 1.0.0  
**Date:** November 11, 2026  

---

## 1. REST API ENDPOINT REFERENCE (`backend/app/api/v1_router.py`)

Base Path: `http://localhost:8000/api/v1`

### 1.1 Health & Status APIs
- **`GET /health`**
  - **Description:** Returns backend health, version, and connectivity status for Kubernetes and Prometheus.
  - **Response Schema:**
    ```json
    {
      "status": "ok",
      "service": "dpbps-backend",
      "version": "0.1.0",
      "kubernetes_connected": true,
      "prometheus_connected": true,
      "dry_run": true
    }
    ```

- **`GET /scaling/status`**
  - **Description:** Returns continuous controller loop state, active deployment phase, and current scaling configuration.
  - **Response Schema:**
    ```json
    {
      "simulation_mode": true,
      "dry_run": true,
      "scaling_enabled": false,
      "phase": "NORMAL_OPERATION",
      "config": {
        "min_replicas": 1,
        "max_replicas": 3,
        "cooldown_sec": 60,
        "max_replica_change": 1
      },
      "latest_decision": { ... }
    }
    ```

### 1.2 Microservice Observability APIs
- **`GET /services`**
  - **Description:** Returns real-time metrics for all 10 Online Boutique microservices.
  - **Response Schema:** Array of `ServiceStatusResponse`:
    ```json
    [
      {
        "id": "productcatalogservice",
        "name": "productcatalogservice",
        "environment_id": "online-boutique",
        "health": "HEALTHY",
        "ready_replicas": 1,
        "desired_replicas": 1,
        "cpu_utilisation": 0.008,
        "memory_utilisation": 0.129,
        "request_rate": 0.0,
        "p95_latency": 4.8,
        "error_rate": 0.0,
        "telemetry_available": true,
        "deployment_phase": "NORMAL_OPERATION"
      }
    ]
    ```

- **`GET /topology`**
  - **Description:** Returns microservice dependency graph nodes and directed invocation edges for visualization.

### 1.3 Scaling Operations & Control APIs
- **`POST /scaling/actuator/execute`**
  - **Description:** Manually executes a validated scaling decision through the actuator.
  - **Request Body:** `DecisionOutput` model.

- **`POST /scaling/actuator/emergency-stop`**
  - **Description:** Triggers fail-closed emergency stop switch, instantly halting all actuator modifications.
  - **Request Body:** `{"reason": "Manual operator override"}`

- **`POST /scaling/actuator/resume`**
  - **Description:** Resumes actuator operations following an emergency stop.

### 1.4 CI/CD Deployment Lifecycle APIs
- **`POST /deployments/webhook`**
  - **Description:** Ingests deployment phase lifecycle webhooks from CI/CD runners (e.g. GitHub Actions, ArgoCD).
  - **Headers Required:** `X-Hub-Signature-256: sha256=<hmac>`
  - **Request Body:**
    ```json
    {
      "service_name": "productcatalogservice",
      "phase": "ACTIVE_DEPLOYMENT",
      "version": "v1.1.0",
      "timestamp": "2026-11-11T17:34:12Z"
    }
    ```

---

## 2. PYTHON CORE COMPONENT REFERENCE

### 2.1 `ContinuousDPBPSController` (`backend/scaling/continuous_controller.py`)
- **`start() -> bool`**: Asynchronously launches the continuous evaluation loop.
- **`stop() -> bool`**: Gracefully cancels the background loop task.
- **`run_single_cycle() -> ContinuousCycleSummary`**: Executes a single atomic closed-loop evaluation cycle.
- **`get_status() -> ContinuousControllerStatus`**: Returns runtime loop diagnostic metrics.

### 2.2 `KubernetesScalingActuator` (`backend/scaling/kubernetes/actuator.py`)
- **`execute_decision(decision: DecisionOutput) -> KubernetesScalingResult`**: Executes or simulates a single scaling action with complete safety gate checks.
- **`verify_post_action_readiness(service: str, target: int, timeout: float) -> dict`**: Polls Kubernetes Deployment status until all target pods achieve `Ready` state.
- **`execute_rollback_procedure(service: str, rollback_replicas: int, reason: str) -> dict`**: Automatically patches deployment back to baseline replica count upon readiness timeout.
- **`activate_emergency_stop(reason: str) -> None`**: Engages global emergency lock.
- **`deactivate_emergency_stop() -> None`**: Disengages global emergency lock.

### 2.3 `KubernetesTelemetryAdapter` (`backend/scaling/kubernetes/telemetry_adapter.py`)
- **`collect_deployment_telemetry() -> List[Dict[str, Any]]`**: Ingests raw metrics from Prometheus and Kubernetes Metrics Server across all namespace deployments.
- **`get_telemetry_inputs() -> Tuple[List[TelemetryInput], List[Dict]]`**: Produces validated, normalized `TelemetryInput` objects, partitioning missing/stale streams into `excluded_telemetry`.

### 2.4 `DeploymentStateManager` (`backend/scaling/deployment_state.py`)
- **`set_phase(phase: DeploymentPhase, service_name: Optional[str]) -> None`**: Sets global or per-service rollout phase.
- **`can_scale(service_name: str, now: datetime, config: ScalingConfig) -> bool`**: Evaluates anti-flapping cooldown window (returns True if $(t - t_{last}) \ge \tau_{cooldown}$).
- **`is_stabilized_for_scale_down(service: str, now: datetime, config: ScalingConfig) -> bool`**: Enforces post-deployment stabilization delay (60s).

---

## 3. FRONTEND CLIENT API REFERENCE (`frontend/src/services/api.ts`)

| TypeScript Method | HTTP Method | Endpoint | Return Type | UI Consumer |
| :--- | :--- | :--- | :--- | :--- |
| `getSystemHealth()` | `GET` | `/health` | `SystemHealth` | AppLayout TopNav status pill |
| `getServices()` | `GET` | `/services` | `Service[]` | ServicesPage, OverviewDashboard |
| `getTopology()` | `GET` | `/topology` | `TopologyData` | ServiceTopologyPage |
| `getBottlenecks()` | `GET` | `/bottlenecks` | `BottleneckResponse`| BottleneckAnalysisPage |
| `getScalingStatus()`| `GET` | `/scaling/status`| `ScalingStatus` | ScalingPage, DpbpsIntelligencePage |
| `getScalingHistory()`| `GET`| `/scaling/history`| `ScalingHistoryRecord[]` | ScalingHistoryPage |
| `getDeployments()` | `GET` | `/deployments` | `Deployment[]` | DeploymentsPage |
| `getAnalytics()` | `GET` | `/analytics` | `AnalyticsData` | PerformanceAnalyticsPage |
| `triggerEmergencyStop()`| `POST` | `/scaling/actuator/emergency-stop` | `ActuatorResponse` | ScalingPage Emergency Button |
| `resumeActuator()` | `POST` | `/scaling/actuator/resume` | `ActuatorResponse` | ScalingPage Resume Button |

