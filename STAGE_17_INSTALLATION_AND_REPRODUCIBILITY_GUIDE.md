# STAGE 17 — INSTALLATION AND REPRODUCIBILITY GUIDE
# COMPLETE OPERATIONAL RUNBOOK FOR THE DPBPS AUTOSCALING PLATFORM

**Project Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Framework:** DPBPS  
**Document Version:** 1.0.0 (Public Artifact & Reproducibility Package)  
**Date:** November 11, 2026  

---

## 1. SYSTEM REQUIREMENTS & PREREQUISITES

| Dependency | Required Version | Verification Command | Purpose |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 10/11 or Linux | `systeminfo` / `uname -a` | Host environment |
| **Python** | 3.11.x (x64) | `python --version` | Backend API & evaluation engines |
| **Node.js** | 18.x or 20.x | `node --version` | Frontend dashboard & tooling |
| **npm** | 9.x or 10.x | `npm --version` | Node package manager |
| **Kubernetes (kind)** | v1.28+ (Tested on v1.34.3) | `kubectl version --client` | Microservices target cluster |
| **Prometheus** | v2.45+ (kube-prom-stack) | `curl http://localhost:9090/-/healthy` | Observability & metrics scraper |
| **Metrics Server** | v0.6+ | `kubectl top nodes` | Pod CPU & RAM metrics |

---

## 2. REPOSITORY INSTALLATION & SETUP

### 2.1 Workspace Directory Structure
Navigate to the root workspace directory:
```bash
cd "D:\CIS\Deployment Aware AAutoscaling Platform"
```

### 2.2 Python Backend Environment Setup
Install required Python dependencies:
```bash
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```
Key packages installed: `fastapi`, `uvicorn`, `pydantic`, `kubernetes`, `urllib3`, `requests`, `pytest`, `pytest-asyncio`, `matplotlib`.

### 2.3 Frontend Dashboard Setup
Install required Node.js packages and build assets:
```bash
cd frontend
npm install
npm run build
cd ..
```

---

## 3. AUTOMATED REGRESSION & TEST SUITE EXECUTION

### 3.1 Backend Test Suite (221 Automated Tests)
Run the complete regression suite verifying controllers, state manager, actuator safety, telemetry adapters, and API routers:
```powershell
cmd /c "set PYTHONPATH=. && python -m pytest backend/tests -v"
```
*Expected Output:* `221 passed, 2 skipped in ~8.5 seconds`.

### 3.2 Frontend TypeScript Type-Checking & Production Build
```powershell
cd frontend
npm run build
```
*Expected Output:* `tsc -b && vite build` completes in `< 3.0s` with `0 errors`.

---

## 4. LAUNCHING THE LIVE PLATFORM DAEMONS

To run the complete platform locally with live Kubernetes telemetry and frontend visualization:

### 4.1 Step 1: Start Prometheus Port-Forward (Background Task)
Expose the Kubernetes Prometheus server locally on port 9090:
```powershell
kubectl port-forward svc/dpbps-monitoring-kube-prom-prometheus -n monitoring 9090:9090
```
Verify resolution: `curl http://127.0.0.1:9090/api/v1/query?query=up` returns `status=success`.

### 4.2 Step 2: Start the FastAPI Backend Server
Launch the backend REST API daemon on port 8000:
```powershell
cmd /c "set PYTHONPATH=. && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
```
Verify health: `curl http://127.0.0.1:8000/api/v1/health` returns `status: "ok"`, `kubernetes_connected: true`, `prometheus_connected: true`.

### 4.3 Step 3: Start the React Frontend Dashboard
Launch the Vite development server on port 5173:
```powershell
cd frontend
npm run dev
```
Open your browser to: `http://localhost:5173`.

---

## 5. REPRODUCING EXPERIMENTS AND EVALUATION RESULTS

### 5.1 Reproducing the Stage 16 Comparative Evaluation (Tier 3)
Execute the complete 160-evaluation comparative benchmark across all 4 policies and 8 scenarios:
```powershell
cmd /c "set PYTHONPATH=. && python backend/evaluation/stage16_evaluation.py"
```
- **Generated Dataset:** `results/evaluation/stage16_evaluation_dataset.json`
- **Generated Plots:** `results/evaluation/plots/*.png` (12 high-resolution comparison charts).

### 5.2 Reproducing Controlled Live Kubernetes Scaling (Tier 1)
To execute the authorized controlled physical replica mutation ($1 \to 2 \to 1$) on `productcatalogservice`:
```powershell
cmd /c "set PYTHONPATH=. && python backend/evaluation/stage15_live_scaling_experiment.py"
```
- **Execution Flow:** Quiescent evaluation (`HOLD`) $\to$ Bottleneck scale-up ($1 \to 2$ in $18.18\text{s}$) $\to$ Cooldown enforcement ($60\text{s}$) $\to$ Restoration scale-down ($2 \to 1$ in $2.05\text{s}$).
- **Generated Measurements:** `results/experiments/STAGE_15_1_RAW_MEASUREMENTS.json`.

---

## 6. FAIL-SAFE EMERGENCY PROCEDURES

If manual intervention is required during any live execution:
1. **Dashboard Emergency Button:** Click **"Trigger Emergency Stop"** on the `/scaling` page.
2. **REST API Emergency Override:**
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/scaling/actuator/emergency-stop -H "Content-Type: application/json" -d "{\"reason\": \"Manual operator intervention\"}"
   ```
3. **Direct Kubernetes Fallback:**
   ```powershell
   kubectl scale deployment productcatalogservice --replicas=1 -n online-boutique
   ```

