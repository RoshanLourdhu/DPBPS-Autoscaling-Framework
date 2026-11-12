# STAGE 10.4 — SERVICE TOPOLOGY PAGE REDESIGN REPORT

**Project**: DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research Title**: "Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices"  
**Repository**: `D:\CIS\Deployment Aware AAutoscaling Platform`  
**Date**: November 11, 2026  
**Status**: **IMPLEMENTATION COMPLETE & VERIFIED**

---

## 1. Executive Summary

Stage 10.4 successfully implements the complete, enterprise-grade redesign of the **Service Topology** page (`/topology`) for the DPBPS Autoscaling Platform.

The redesigned interface provides an interactive, directed call-graph (DAG) visualization of the Google Cloud Platform Online Boutique application. It structures the 10 microservices across 4 logical architectural tiers, renders the 14 verified gRPC/HTTP call edges using smooth cubic Bézier curves, enables interactive canvas navigation (smooth mouse-drag panning, scroll-wheel zooming, reset-view controls), exposes at-a-glance container telemetry directly on node cards, visualizes backend-identified DPBPS bottleneck propagation, and opens an in-depth Service Inspector side panel upon node selection.

All implementations strictly consume live backend API contracts with zero metric fabrication. TypeScript validation and production builds compile with zero errors.

---

## 2. Phase 1 — Architecture Audit & Dependency Data Sources

### A. Authoritative Microservices List (10 Services)
Audited from `backend/scaling/kubernetes/telemetry_adapter.py` (`ONLINE_BOUTIQUE_DEPENDENCIES`) and `v1_router.py`:
1. `frontend` (Client Ingress / Edge Proxy)
2. `checkoutservice` (Order Checkout Coordinator)
3. `recommendationservice` (Product Recommendations)
4. `cartservice` (Shopping Cart State Manager)
5. `productcatalogservice` (Catalog Database & Inventory)
6. `currencyservice` (Exchange Rate Converter)
7. `paymentservice` (Payment Processing Gateway)
8. `shippingservice` (Shipping Cost & Fulfillment)
9. `emailservice` (Order Confirmation Dispatcher)
10. `adservice` (Targeted Advertising Provider)

### B. Verified Directed Call Edges (14 Edges)
Audited directly from `ONLINE_BOUTIQUE_DEPENDENCIES`:
- `frontend` $\to$ `checkoutservice`, `recommendationservice`, `cartservice`, `productcatalogservice`, `currencyservice`, `shippingservice`, `adservice` (7 outgoing edges)
- `checkoutservice` $\to$ `cartservice`, `productcatalogservice`, `currencyservice`, `paymentservice`, `shippingservice`, `emailservice` (6 outgoing edges)
- `recommendationservice` $\to$ `productcatalogservice` (1 outgoing edge)
- Leaf services (`productcatalogservice`, `currencyservice`, `paymentservice`, `shippingservice`, `emailservice`, `adservice`) have 0 outgoing application microservice calls.
- Total verified application call edges: **14 directed paths**.

### C. Available API Endpoints & Telemetry Fields
- `/api/v1/services`: Returns `ServiceInfo[]` with live `cpu_utilisation`, `memory_utilisation`, `request_rate`, `p95_latency`, `error_rate`, `ready_replicas`, `desired_replicas`, `dependencies`, and `telemetry_available`.
- `/api/v1/dpbps/pipeline/evaluate`: Returns `PipelineEvaluationResponse` with `bottleneck_service`, `scale_up_count`, `scale_down_count`, `hold_count`, and per-service `PipelineServiceResult` (containing `dpbps_decision`, `proposed_replica_count`, `reason`, `actuator_execution_status`).

---

## 3. Implemented Features & Architecture

### A. Interactive 4-Tier Topology Canvas
- **Tier 1 (Client Ingress)**: `frontend` positioned at coordinate $(x: 40, y: 280)$.
- **Tier 2 (Domain Orchestration & Aggregation)**: `checkoutservice` $(x: 300, y: 130)$ and `recommendationservice` $(x: 300, y: 440)$.
- **Tier 3 (State & Caching)**: `cartservice` $(x: 570, y: 70)$.
- **Tier 4 (Core Domain & Infrastructure Services)**: 6 leaf microservices distributed vertically from $y: 30$ to $y: 530$ at $x: 850$.
- **Background Tier Bands**: Subtle dashed tier columns with labels (`TIER 1 • INGRESS`, `TIER 2 • ORCHESTRATION`, `TIER 3 • STATE STORE`, `TIER 4 • CORE DOMAIN`).

### B. Smooth Bézier Directed Call Edges
- All 14 edges rendered via cubic Bézier paths:
  $$\text{Path: } M (x_1, y_1) \ C (x_1 + 0.45\Delta x, y_1), (x_2 - 0.45\Delta x, y_2), (x_2, y_2)$$
- Directional arrowheads defined in SVG `<defs>` (`markerEnd="url(#arrow-cyan)"`, `markerEnd="url(#arrow-rose)"`).
- **Interactive Highlighting**:
  - Selecting or hovering over any node highlights all incoming callers in amber (`#f59e0b`) and outgoing dependencies in cyan (`#06b6d4`).
  - Unrelated edges are automatically dimmed to $0.12$ opacity.

### C. Canvas Navigation & Controls
- **Panning**: Click and drag anywhere on the canvas background to pan in any direction.
- **Zooming**: Smooth wheel zoom (clamped between $65\%$ and $180\%$) plus dedicated `Zoom In` ($+$) and `Zoom Out` ($-$) buttons.
- **Reset Layout**: Single-click `Reset View` button restores zoom to $100\%$ and pans back to $(0,0)$.
- **Search & Filter**: Real-time search bar filters nodes by name. Quick status filters (`All`, `Bottlenecks`, `Under Pressure`, `Healthy`) highlight matching nodes while dimming non-matches.

### D. Node Cards with Live At-a-Glance Telemetry
Each SVG node card ($166 \times 58\text{ px}$) displays:
- Severity status dot (Emerald = Healthy, Amber = Under Pressure, Rose = Identified Bottleneck, Slate = Insufficient Telemetry).
- Microservice name.
- Bottleneck tag badge (`BOT`) when detected.
- Monospace bottom metrics ribbon:
  - `REP`: Ready Replicas / Desired Replicas (e.g. `1/1`)
  - `CPU`: CPU utilization percentage (turns rose if $\ge 70\%$)
  - `P95`: P95 latency in milliseconds (turns rose if $> 200\text{ ms}$)

### E. Service Inspector Side Panel
Selecting any node opens a deep-dive inspection card containing:
1. **Header**: Name, namespace `online-boutique`, status badge, active deployment phase.
2. **Bottleneck Alert**: Prominent notice if the service is identified as the primary system bottleneck.
3. **Telemetry Quad Grid**: Replicas (`ready / desired`), Throughput (`req/s`), P95 Latency (`ms`), CPU Utilization (`%`), Memory Utilization (`%`), Error Rate (`%`).
4. **Interactive Incoming Callers**: Lists all upstream services with click-to-select capability.
5. **Interactive Outgoing Dependencies**: Lists all downstream dependencies with click-to-select capability.
6. **DPBPS Scaling Decision**: Action badge (`SCALE_UP`, `HOLD`, `SCALE_DOWN`), proposed replica count ($N \to M$), controller reason string, and actuator validation mode (`DRY_RUN`).
7. **Direct Navigation Links**: Quick deep links to `/services` and `/bottlenecks`.

### F. DPBPS Bottleneck Visualization
Strictly derives bottleneck severity from verified backend outputs without inventing mock thresholds:
- **Critical Bottleneck**: Matches `pipeline.bottleneck_service`. Triggers pulsing rose border on the node and animates incoming call paths with dashed rose lines to visualize upstream bottleneck propagation.
- **Under Pressure**: Matches services receiving `SCALE_UP` recommendation from DPBPS or exhibiting high CPU ($\ge 70\%$).
- **Insufficient Telemetry**: Identifies services with `telemetry_available: false` or `EXCLUDED` status.
- **Healthy**: Services operating within nominal bounds.

---

## 4. Verification and Build Results

### A. TypeScript & Production Build Verification
Executed: `npm --prefix "frontend" run build` (`tsc -b && vite build`):
```text
> frontend@0.0.0 build
> tsc -b && vite build

vite v8.3.5 building client environment for production...
transforming...
✓ 2138 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.45 kB │ gzip:   0.29 kB
dist/assets/index-BeoaKEhH.css   38.81 kB │ gzip:   7.32 kB
dist/assets/index-CCtXXnWJ.js   775.86 kB │ gzip: 210.92 kB

✓ built in 3.60s
```
**Result**: Build succeeded in **3.60s** with **0 TypeScript or Vite compilation errors**.

### B. Linter Verification
Executed: `npm --prefix "frontend" run lint` (`oxlint`):
- **0 errors** across 36 files.
- **Result**: **PASS**.

### C. Safety and Environmental Isolation
- **Backend Code**: No files in `backend/` were touched.
- **Kubernetes Resources**: No cluster pods or manifests were touched.
- **Scaling Posture**: `SCALING_ENABLED=false` and actuator `DRY_RUN=True` remain intact.
- **Load Generation**: `loadgenerator` replica count remains at 0.
- **Git State**: No commits or pushes have been made.

---

## 5. Known Limitations

- **Browser Context**: Full visual browser rendering requires running outside sandbox (`BypassSandbox: true`), which is kept off during build/audit steps.
- **Redis Cache Node**: `cartservice` connects to `redis-cart`. In accordance with prompt instructions to only render verified application microservices, the topology DAG is scoped to the 10 core Online Boutique microservices, noting Redis as infrastructure cache in cartservice inspection details.

