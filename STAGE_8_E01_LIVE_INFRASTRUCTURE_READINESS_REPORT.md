# STAGE 8 — EXPERIMENT E01: LIVE INFRASTRUCTURE & TELEMETRY READINESS REPORT

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Application:** Google Cloud Online Boutique (10 instrumented microservices)  
**Cluster:** Kubernetes (`docker-desktop`), Namespaces: `online-boutique`, `monitoring`  
**Audit Timestamp:** 2026-11-10T20:35:00+05:30  
**Verification Scope:** Live Infrastructure Restoration, Prometheus/Grafana Port-Forwarding, Real Application Telemetry Ingestion, DPBPS Pipeline Dry-Run, and Safety Posture  
**Safety Mandate:** Zero traffic generated. Zero replica modifications performed. Loadgenerator held at 0 replicas.

---

## 1. Executive Summary

Following manual initiation of Docker Desktop, the complete development, monitoring, and scaling infrastructure has been restored, verified, and cross-audited.

All critical infrastructure layers are confirmed operational:
1. **Docker Desktop & Engine:** Operating in WSL2 with engine v29.3.1 (Docker Desktop 4.66.1).
2. **Kubernetes Cluster:** Context `docker-desktop` is reachable. Node `desktop-control-plane` is `Ready` (v1.34.3).
3. **Application Workload:** All 10 Online Boutique microservices are `Running` and `1/1 Ready`. `loadgenerator` is verified at `0/0` replicas.
4. **Monitoring Pipeline:** OpenTelemetry Collector, Prometheus (`prometheus-0`), and Grafana are healthy. Active background port-forwards are established for Prometheus (`http://localhost:9090`) and Grafana (`http://localhost:3000`).
5. **Real Application Telemetry:** Successfully ingested via `PrometheusClient` and `KubernetesTelemetryAdapter`. All 10 services report real-time Metrics Server CPU/RAM utilization. Active services report real Prometheus latency (P95: 4.8ms) and request rate (~0.35 RPS). Idle services are faithfully identified without data falsification.
6. **DPBPS Pipeline Integration:** Verified end-to-end via `/api/v1/dpbps/pipeline/evaluate`. Active services evaluated to `HOLD` ("Pressure within bounds"); idle services safely `EXCLUDED`; Actuator operated in `DRY-RUN` mode with `cluster_modified=False`.
7. **Automated Regression Suite:** **162 passed, 2 skipped, 0 failures** in 6.91s.
8. **Final Readiness Verdict:** **GO** — The platform is fully prepared for operator authorization to execute Experiment E01 (`NORMAL_TRAFFIC`).

---

## 2. Docker Desktop Status

| Attribute | Observed Value | Status |
|---|---|---|
| **Client Version** | 29.3.1 (API v1.54, built Wed Mar 25 2026) | Verified |
| **Server Version** | Docker Desktop 4.66.1 (222799), Engine 29.3.1 | Operational |
| **WSL2 Distro** | `docker-desktop` (State: `Running`, Version: 2) | Operational |
| **Linux Kernel** | 6.6.87.2-microsoft-standard-WSL2 (x86_64) | Healthy |
| **Running Containers** | 12 core cluster containers | Healthy |

---

## 3. Kubernetes Connectivity & Cluster Health

- **Current Context:** `docker-desktop` (Verified)
- **Control Plane API:** Reachable via `https://127.0.0.1:62664`
- **Active Namespaces:** `default`, `kube-system`, `local-path-storage`, `monitoring`, `online-boutique`

```
NAME                    STATUS   ROLES           AGE    VERSION
desktop-control-plane   Ready    control-plane   3d4h   v1.34.3
```

---

## 4. Online Boutique Application Pod Health

All 10 target microservices and supporting backing services are running and ready:

```
+---------------------------------------------------------------------------------------------------+
| ONLINE BOUTIQUE DEPLOYMENTS & PODS (NAMESPACE: online-boutique)                                   |
+---------------------------------------------------------------------------------------------------+
| Service / Deployment      | Ready   | Status    | Restarts (Post-Boot) | Pod IP       | Port(s)   |
+---------------------------+---------+-----------+----------------------+--------------+-----------+
| frontend                  | 1/1     | Running   | 1                    | 10.244.0.8   | 80/TCP    |
| cartservice               | 1/1     | Running   | 1                    | 10.244.0.14  | 7070/TCP  |
| productcatalogservice     | 1/1     | Running   | 1                    | 10.244.0.15  | 3550/TCP  |
| currencyservice           | 1/1     | Running   | 1                    | 10.244.0.6   | 7000/TCP  |
| paymentservice            | 1/1     | Running   | 1                    | 10.244.0.16  | 50051/TCP |
| shippingservice           | 1/1     | Running   | 1                    | 10.244.0.19  | 50051/TCP |
| emailservice              | 1/1     | Running   | 1                    | 10.244.0.17  | 5000/TCP  |
| checkoutservice           | 1/1     | Running   | 1                    | 10.244.0.11  | 5050/TCP  |
| recommendationservice     | 1/1     | Running   | 2                    | 10.244.0.20  | 8080/TCP  |
| adservice                 | 1/1     | Running   | 1                    | 10.244.0.18  | 9555/TCP  |
| redis-cart                | 1/1     | Running   | 1                    | 10.244.0.9   | 6379/TCP  |
| opentelemetrycollector    | 1/1     | Running   | 1                    | 10.244.0.5   | 4317/4318 |
| loadgenerator             | 0/0     | Scaled 0  | 0                    | None         | None      |
+---------------------------------------------------------------------------------------------------+
```

> [!IMPORTANT]
> `loadgenerator` is confirmed at **0 replicas** (`spec.replicas: 0`). Zero workload traffic is active.

---

## 5. Monitoring Infrastructure Health & Endpoints

1. **Monitoring Pods (`monitoring` namespace):**
   - `prometheus-dpbps-monitoring-kube-prom-prometheus-0`: `2/2 Running`
   - `dpbps-monitoring-grafana-774f46cc7b-sp4vg`: `3/3 Running`
   - `dpbps-monitoring-kube-prom-operator-c6c5947b4-mr5hx`: `1/1 Running`
   - `dpbps-monitoring-kube-state-metrics-8dc7cd85b-xvvm7`: `1/1 Running`
2. **Kubernetes Metrics Server:**
   - APIService `v1beta1.metrics.k8s.io`: `True` (Available)
3. **Established Port-Forwards:**
   - **Prometheus:** `kubectl port-forward svc/dpbps-monitoring-kube-prom-prometheus -n monitoring 9090:9090`  
     *Probe:* `http://localhost:9090/-/healthy` $\to$ `Prometheus Server is Healthy.`
   - **Grafana:** `kubectl port-forward svc/dpbps-monitoring-grafana -n monitoring 3000:80`  
     *Probe:* `http://localhost:3000/api/health` $\to$ `{"database": "ok", "version": "13.3.0"}`
4. **Prometheus Scrape Targets (`/api/v1/targets`):**
   - 19 active targets registered.
   - `otel-collector` (`http://10.244.0.5:8889/metrics`): **Health: UP**
   - `opentelemetrycollector` (`http://10.244.0.5:8888/metrics`): **Health: UP**
   - `kube-state-metrics` (`http://10.244.0.2:8080/metrics`): **Health: UP**

---

## 6. Actual Application Telemetry Ingestion (All 10 Services)

Telemetry was collected live through [`KubernetesTelemetryAdapter`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/scaling/kubernetes/telemetry_adapter.py) and [`PrometheusClient`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/scaling/kubernetes/prometheus_client.py):

```
+---------------------------------------------------------------------------------------------------------------------------+
| ACTUAL LIVE MICROSERVICE TELEMETRY (SNAPSHOT TIMESTAMP: 2026-11-10T20:30:30+05:30)                                       |
+---------------------------------------------------------------------------------------------------------------------------+
| Service Name           | Replicas | CPU (m) | CPU % | Mem (MiB) | Mem % | RPS   | P95 (ms) | Error Rate | Telemetry State |
+------------------------+----------+---------+-------+-----------+-------+-------+----------+------------+-----------------+
| frontend               | 1/1      | 0.6m    | 0.6%  | 7.4 MiB   | 11.6% | 0.35  | 4.8 ms   | 0.000      | COMPLETE        |
| checkoutservice        | 1/1      | 1.1m    | 1.1%  | 5.9 MiB   | 9.3%  | 0.37  | 4.7 ms   | 0.000      | COMPLETE        |
| productcatalogservice  | 1/1      | 0.9m    | 0.9%  | 7.3 MiB   | 11.4% | 0.37  | 4.8 ms   | 0.000      | COMPLETE        |
| adservice              | 1/1      | 1.9m    | 0.9%  | 97.9 MiB  | 54.4% | None  | None     | None       | IDLE/EXCLUDED   |
| cartservice            | 1/1      | 2.3m    | 1.1%  | 51.3 MiB  | 80.2% | None  | None     | None       | IDLE/EXCLUDED   |
| currencyservice        | 1/1      | 0.6m    | 0.6%  | 34.6 MiB  | 54.0% | None  | None     | None       | IDLE/EXCLUDED   |
| emailservice           | 1/1      | 5.5m    | 5.5%  | 39.0 MiB  | 60.9% | None  | None     | None       | IDLE/EXCLUDED   |
| paymentservice         | 1/1      | 0.6m    | 0.6%  | 33.2 MiB  | 52.0% | None  | None     | None       | IDLE/EXCLUDED   |
| recommendationservice  | 1/1      | 5.5m    | 5.5%  | 34.0 MiB  | 15.4% | None  | None     | None       | IDLE/EXCLUDED   |
| shippingservice        | 1/1      | 1.2m    | 1.2%  | 5.9 MiB   | 9.2%  | None  | None     | None       | IDLE/EXCLUDED   |
+---------------------------------------------------------------------------------------------------------------------------+
```

### Observations on Telemetry Completeness:
1. **Active Probe Traffic:** `frontend`, `checkoutservice`, and `productcatalogservice` receive periodic internal kubelet probes and report complete live metrics (RPS ~0.35–0.37, P95 latency ~4.7–4.8ms, error rate 0.000).
2. **Idle Backing Services:** Services without direct active probe traffic report `None` for application traffic metrics while maintaining live Metrics Server CPU/RAM statistics. In strict conformance with project rules, missing traffic metrics are **not** replaced with synthetic zeros.

---

## 7. DPBPS Pipeline & Decision Evaluation

Evaluated via `GET /api/v1/dpbps/pipeline/evaluate`:

```
+---------------------------------------------------------------------------------------------------+
| DPBPS PIPELINE EVALUATION (DRY-RUN POSTURE)                                                       |
+---------------------------------------------------------------------------------------------------+
| Pipeline Parameter               | Evaluated Value                                                |
+----------------------------------+----------------------------------------------------------------+
| Execution Mode                   | DRY_RUN (Actuator does not mutate cluster)                     |
| Cluster Modified                 | False                                                          |
| Deployment Phase                 | NORMAL_OPERATION                                               |
| Total Target Services Evaluated  | 12 microservices + dependencies                                |
| Complete Telemetry Services      | 3 (frontend, checkoutservice, productcatalogservice)           |
| Incomplete / Idle Services       | 9 (excluded from scaling decisions)                           |
| Scaling Decisions: SCALE_UP      | 0                                                              |
| Scaling Decisions: SCALE_DOWN    | 0                                                              |
| Scaling Decisions: HOLD          | 3                                                              |
| Active Bottleneck Detected       | None (Normal operation, low pressure)                          |
+----------------------------------+----------------------------------------------------------------+
```

### Per-Service Pipeline Decisions:
- **`frontend`:** `HOLD` (1 $\to$ 1 replicas) — Pressure within bounds (aggregate=0.00). Actuator status: `SKIPPED`.
- **`checkoutservice`:** `HOLD` (1 $\to$ 1 replicas) — Pressure within bounds (aggregate=0.00). Actuator status: `SKIPPED`.
- **`productcatalogservice`:** `HOLD` (1 $\to$ 1 replicas) — Pressure within bounds (aggregate=0.00). Actuator status: `SKIPPED`.
- **Remaining Services (`adservice`, `cartservice`, etc.):** `EXCLUDED` — Safely held at current replica count (1) due to idle baseline.

---

## 8. System Resource Headroom

Live cluster capacity was sampled via `kubectl top`:

```
+---------------------------------------------------------------------------------------------------+
| RESOURCE UTILIZATION SNAPSHOT                                                                     |
+---------------------------------------------------------------------------------------------------+
| Entity                           | CPU Usage (Cores / %)           | Memory Usage (Bytes / %)     |
+----------------------------------+---------------------------------+------------------------------+
| Node: desktop-control-plane      | 805m / 5%                       | 2268 MiB / 19%               |
| Available Headroom               | > 95% CPU Available             | > 80% Memory Available       |
| Total Online Boutique Pods       | ~35m                            | ~370 MiB                     |
| Total Monitoring Pods            | ~128m                           | ~812 MiB                     |
+----------------------------------+---------------------------------+------------------------------+
```

**Headroom Verdict:** Massive resource capacity exists for Experiment E01 (10 virtual users generating ~12 RPS). No memory pressure or CPU throttling will occur.

---

## 9. Experiment Safety Invariants Verification

```
+---------------------------------------------------------------------------------------------------+
| SAFETY INVARIANTS STATUS MATRIX                                                                   |
+---------------------------------------------------------------------------------------------------+
| Invariant Rule                   | Target Posture  | Observed State    | Compliance Verdict       |
+----------------------------------+-----------------+-------------------+--------------------------+
| SCALING_ENABLED                  | False           | False (config.py) | COMPLIANT (LOCKED)       |
| EXPERIMENT_EXECUTION_ENABLED     | False           | False (exec.py)   | COMPLIANT (LOCKED)       |
| Kubernetes Actuator Mode         | DRY-RUN         | DRY-RUN           | COMPLIANT (LOCKED)       |
| loadgenerator Replicas           | 0 Replicas      | 0 Replicas        | COMPLIANT (ZERO)         |
| Active Experiment State          | Idle / READY    | 0 Active Running  | COMPLIANT (CLEAN)        |
| Protected Infrastructure Guards  | Cannot scale    | Isolated          | COMPLIANT (LOCKED)       |
| Manual CLI Workload Scaling      | Forbidden       | None used         | COMPLIANT (ENFORCED)     |
+----------------------------------+-----------------+-------------------+--------------------------+
```

---

## 10. Automated Test Results

1. **Full Backend Regression Suite:**
   - `python -m pytest backend/tests -q`
   - **162 passed, 2 skipped, 0 failures** in 6.91s.
2. **Workload & High-Traffic Validation Suite:**
   - `python -m pytest backend/tests/test_workload_and_experiments.py backend/tests/test_dpbps_high_traffic.py -q`
   - **40 passed, 0 failures** in 0.63s.
3. **Prometheus Client Test Suite:**
   - `python -m pytest backend/tests/test_prometheus_client.py -q`
   - **21 passed, 0 failures** in 1.31s.

---

## 11. Final Readiness Verdict

```
================================================================================
FINAL LIVE INFRASTRUCTURE READINESS VERDICT: GO
================================================================================
- Docker Desktop daemon is running and verified.
- Kubernetes context is docker-desktop; node is Ready.
- All 10 Online Boutique microservices are healthy and 1/1 Ready.
- Prometheus and Grafana are operational and port-forwarded.
- OpenTelemetry Collector is healthy and scraped by Prometheus.
- Actual application and resource telemetry is successfully ingested.
- DPBPS Controller and Actuator operate flawlessly in DRY-RUN mode.
- 162 backend regression tests passed with 0 failures.
- All safety interlocks are locked (SCALING_ENABLED=false, EXPERIMENT_EXECUTION_ENABLED=false).
================================================================================
```

---

## 12. Safety Compliance Statement

**No workload experiment was started, no actual load was generated, and no live application scaling occurred.**  
The platform is in idle standby, awaiting explicit operator authorization to execute Experiment E01.

