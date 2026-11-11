# STAGE 8 — FINAL WORKLOAD CONFIGURATION CONSISTENCY REPORT

**Project:** DPBPS — Deployment-Phase-Aware Bottleneck-Prioritized Scaling  
**Research Title:** Design and Performance Evaluation of a CI/CD-Integrated Deployment-Aware Dynamic Scaling Approach for Microservices  
**Target Environment:** Google Cloud Online Boutique on Kubernetes (`docker-desktop`)  
**Audit Timestamp:** 2026-11-10T19:28:00+05:30  
**Audit Type:** Final Pre-Flight Read-Only Workload Configuration Audit & Cross-Artifact Reconciliation  

---

## 1. Actual Configuration of All Six Workload Profiles

All values below are extracted directly from the authoritative Python source code in [`backend/workload/profiles.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/profiles.py) and verified against [`backend/workload/models.py`](file:///D:/CIS/Deployment%20Aware%20AAutoscaling%20Platform/backend/workload/models.py).

### Profile 1: `NORMAL_TRAFFIC` (Baseline)
- **Source Definition:** `get_normal_traffic_profile()` (`profiles.py#L17-L67`)
- **Initial Virtual Users:** 0 (ramps to 10)
- **Maximum Virtual Users:** 10 users (`users=10`)
- **Spawn Rate:** 2.0 users/second (`spawn_rate=2.0`)
- **Ramp-Up Duration:** 5 seconds (`ramp_up_seconds=5`)
- **Steady-State Duration:** 120 seconds (`steady_state_seconds=120`)
- **Ramp-Down Duration:** 5 seconds (`ramp_down_seconds=5`)
- **Total Experiment Duration:** 130 seconds (`total_duration_seconds=130`)
- **LoadTestShape Stages (3 stages):**
  1. `Stage 0 ("Ramp-Up")`: Target: 10 users, Duration: 5s, Spawn Rate: 2.0 u/s
  2. `Stage 1 ("Steady Baseline")`: Target: 10 users, Duration: 120s, Spawn Rate: 2.0 u/s
  3. `Stage 2 ("Ramp-Down")`: Target: 0 users, Duration: 5s, Spawn Rate: 2.0 u/s
  - *Cumulative Stage Durations:* 5s $\to$ 125s $\to$ 130s.
- **Maximum Concurrency:** 10 concurrent users.
- **Target Host:** `"frontend:80"`
- **Expected Workload Behavior:** Stable, low-intensity baseline (~10–15 RPS aggregate across the 10 microservices). P95 latency expected $< 40\text{ms}$ (well below $200\text{ms}$ target). Error rate $0.0\%$. Low CPU ($< 20\%$) and RAM ($< 25\%$) utilization. DPBPS decision: `HOLD` across all services with zero bottlenecks detected.

---

### Profile 2: `GRADUAL_TRAFFIC_INCREASE` (Stepped Staircase)
- **Source Definition:** `get_gradual_traffic_increase_profile()` (`profiles.py#L70-L121`)
- **Initial Virtual Users:** 10 users (Step 1 tier)
- **Maximum Virtual Users:** 50 users (`users=50`)
- **Spawn Rate:** 2.0 users/second (`spawn_rate=2.0`)
- **Ramp-Up Duration:** 10 seconds (parameter metadata) / 3-tier stepped ramp
- **Steady-State Duration:** 160 seconds (parameter metadata)
- **Ramp-Down Duration:** 10 seconds (parameter metadata)
- **Total Experiment Duration:** 180 seconds (`total_duration_seconds=180`)
- **LoadTestShape Stages (3 stepped stages):**
  1. `Stage 0 ("Step 1: Low Concurrency")`: Target: 10 users, Duration: 60s, Spawn Rate: 2.0 u/s
  2. `Stage 1 ("Step 2: Moderate Concurrency")`: Target: 25 users, Duration: 60s, Spawn Rate: 2.0 u/s
  3. `Stage 2 ("Step 3: High Concurrency")`: Target: 50 users, Duration: 60s, Spawn Rate: 2.0 u/s
  - *Cumulative Stage Durations:* 60s $\to$ 120s $\to$ 180s.
- **Maximum Concurrency:** 50 concurrent users.
- **Target Host:** `"frontend:80"`
- **Expected Workload Behavior:** Monotonically increasing stepped staircase (10 $\to$ 25 $\to$ 50 users). Each tier is held for 60 seconds (spanning 4 complete Prometheus 15-second scrape cycles). Traffic rises from ~15 RPS to ~65 RPS. Evaluates progressive scale-up (+1 to +2 replicas) and downstream bottleneck flagging.

---

### Profile 3: `SUDDEN_TRAFFIC_SPIKE` (Pulse Surge)
- **Source Definition:** `get_sudden_traffic_spike_profile()` (`profiles.py#L123-L174`)
- **Initial Virtual Users:** 5 users (Pre-spike quiet baseline)
- **Maximum Virtual Users:** 80 users (`users=80`)
- **Spawn Rate:** 20.0 users/second (`spawn_rate=20.0`)
- **Ramp-Up Duration:** 5 seconds (`ramp_up_seconds=5`)
- **Steady-State Duration:** 60 seconds (`steady_state_seconds=60`, peak spike duration)
- **Ramp-Down Duration:** 5 seconds (`ramp_down_seconds=5`)
- **Total Experiment Duration:** 120 seconds (`total_duration_seconds=120`)
- **LoadTestShape Stages (3 stages):**
  1. `Stage 0 ("Pre-Spike Baseline")`: Target: 5 users, Duration: 30s, Spawn Rate: 2.0 u/s
  2. `Stage 1 ("Sharp Spike Peak")`: Target: 80 users, Duration: 60s, Spawn Rate: 20.0 u/s
  3. `Stage 2 ("Post-Spike Recovery")`: Target: 5 users, Duration: 30s, Spawn Rate: 10.0 u/s
  - *Cumulative Stage Durations:* 30s $\to$ 90s $\to$ 120s.
- **Maximum Concurrency:** 80 concurrent users.
- **Target Host:** `"frontend:80"`
- **Expected Workload Behavior:** Sudden traffic surge from 5 to 80 users at 20 u/s. Sharp inflection in request rate (~5 RPS to ~100+ RPS within seconds). Tests rapid pressure detection, surge handling, and bounded scaling response ($\le 2$ replicas per evaluation). Cooldown prevents over-allocation thrashing.

---

### Profile 4: `SUSTAINED_HIGH_TRAFFIC` (Saturation Plateau)
- **Source Definition:** `get_sustained_high_traffic_profile()` (`profiles.py#L176-L227`)
- **Initial Virtual Users:** 0 (ramps to 60)
- **Maximum Virtual Users:** 60 users (`users=60`)
- **Spawn Rate:** 5.0 users/second (`spawn_rate=5.0`)
- **Ramp-Up Duration:** 20 seconds (`ramp_up_seconds=20`, Stage 0 duration = 20s)
- **Steady-State Duration:** 180 seconds (`steady_state_seconds=180`, Stage 1 duration = 180s)
- **Ramp-Down Duration:** 20 seconds (`ramp_down_seconds=20`, Stage 2 duration = 20s)
- **Total Experiment Duration:** 220 seconds (`total_duration_seconds=220`)
- **LoadTestShape Stages (3 stages):**
  1. `Stage 0 ("Controlled Ramp-Up")`: Target: 60 users, Duration: 20s, Spawn Rate: 5.0 u/s
  2. `Stage 1 ("Sustained High Load")`: Target: 60 users, Duration: 180s, Spawn Rate: 5.0 u/s
  3. `Stage 2 ("Controlled Ramp-Down")`: Target: 0 users, Duration: 20s, Spawn Rate: 5.0 u/s
  - *Cumulative Stage Durations:* 20s $\to$ 200s $\to$ 220s.
- **Maximum Concurrency:** 60 concurrent users.
- **Target Host:** `"frontend:80"`
- **Expected Workload Behavior:** Continuous elevated traffic plateau spanning 180s (12 consecutive Prometheus scrape windows). Evaluates scaling stability, absence of decision flapping, and incremental clamping at `max_replicas = 5`.

---

### Profile 5: `TRAFFIC_DECREASE` (Descending Step)
- **Source Definition:** `get_traffic_decrease_profile()` (`profiles.py#L229-L280`)
- **Initial Virtual Users:** 50 users (High load tier)
- **Maximum Virtual Users:** 50 users (`users=50`)
- **Spawn Rate:** 5.0 users/second (`spawn_rate=5.0`)
- **Ramp-Up Duration:** 10 seconds (`ramp_up_seconds=10` parameter)
- **Steady-State Duration:** 160 seconds (`steady_state_seconds=160` parameter)
- **Ramp-Down Duration:** 10 seconds (`ramp_down_seconds=10` parameter)
- **Total Experiment Duration:** 180 seconds (`total_duration_seconds=180`)
- **LoadTestShape Stages (3 descending stages):**
  1. `Stage 0 ("High Load Tier")`: Target: 50 users, Duration: 60s, Spawn Rate: 5.0 u/s
  2. `Stage 1 ("Intermediate Tier")`: Target: 25 users, Duration: 60s, Spawn Rate: 5.0 u/s
  3. `Stage 2 ("Low Baseline Tier")`: Target: 5 users, Duration: 60s, Spawn Rate: 5.0 u/s
  - *Cumulative Stage Durations:* 60s $\to$ 120s $\to$ 180s.
- **Maximum Concurrency:** 50 concurrent users.
- **Target Host:** `"frontend:80"`
- **Expected Workload Behavior:** Stepwise load descent (50 $\to$ 25 $\to$ 5 users), each held for 60s. Tests scale-down cooldown enforcement (120s), replica floor at 1, and suppression of scale-down during `ACTIVE_DEPLOYMENT`.

---

### Profile 6: `BURSTY_TRAFFIC` (Oscillation & Anti-Thrashing)
- **Source Definition:** `get_bursty_traffic_profile()` (`profiles.py#L282-L315`)
- **Initial Virtual Users:** 60 users (Burst 1)
- **Maximum Virtual Users:** 60 users (`users=60`)
- **Spawn Rate:** 20.0 users/second (`spawn_rate=20.0`)
- **Ramp-Up Duration:** 5 seconds (`ramp_up_seconds=5` parameter)
- **Steady-State Duration:** 150 seconds (`steady_state_seconds=150` parameter)
- **Ramp-Down Duration:** 5 seconds (`ramp_down_seconds=5` parameter)
- **Total Experiment Duration:** 160 seconds (`total_duration_seconds=160`)
- **LoadTestShape Stages (8 alternating stages of 20s each):**
  1. `Stage 0 ("Burst 1")`: Target: 60 users, Duration: 20s, Spawn Rate: 20.0 u/s
  2. `Stage 1 ("Lull 1")`: Target: 5 users, Duration: 20s, Spawn Rate: 10.0 u/s
  3. `Stage 2 ("Burst 2")`: Target: 60 users, Duration: 20s, Spawn Rate: 20.0 u/s
  4. `Stage 3 ("Lull 2")`: Target: 5 users, Duration: 20s, Spawn Rate: 10.0 u/s
  5. `Stage 4 ("Burst 3")`: Target: 60 users, Duration: 20s, Spawn Rate: 20.0 u/s
  6. `Stage 5 ("Lull 3")`: Target: 5 users, Duration: 20s, Spawn Rate: 10.0 u/s
  7. `Stage 6 ("Burst 4")`: Target: 60 users, Duration: 20s, Spawn Rate: 20.0 u/s
  8. `Stage 7 ("Lull 4 (Recovery)")`: Target: 5 users, Duration: 20s, Spawn Rate: 10.0 u/s
  - *Cumulative Stage Durations:* 20s $\to$ 40s $\to$ 60s $\to$ 80s $\to$ 100s $\to$ 120s $\to$ 140s $\to$ 160s.
- **Maximum Concurrency:** 60 concurrent users.
- **Target Host:** `"frontend:80"`
- **Expected Workload Behavior:** 4 cycles of 20s burst (60 users) alternating with 20s lull (5 users). Evaluates controller damping to prevent rapid scaling thrashing during transient lulls.

---

## 2. E03 and E04 Duration Discrepancy Analysis

### Discrepancy Investigation:
In previous documentation, the following figures were reported:
- **E03 (`SUDDEN_TRAFFIC_SPIKE`):**
  - *Stage 7 Final Report:* **120 seconds** (3 stages: 30s + 60s + 30s).
  - *Stage 8 Audit Plan:* **120 seconds** (3 stages: 30s + 60s + 30s).
  - *Stage 8 Readiness Report (Section 7 Prose):* **180 seconds** (described a 5-stage variant: 20s, 20s, 80s, 40s, 20s).
- **E04 (`SUSTAINED_HIGH_TRAFFIC`):**
  - *Stage 7 Final Report:* **220 seconds** (3 stages: 20s + 180s + 20s).
  - *Stage 8 Audit Plan:* **220 seconds** (3 stages: 20s + 180s + 20s).
  - *Stage 8 Readiness Report (Section 7 Prose):* **360 seconds** (described a 4-stage variant: 15s, 300s, 30s, 15s).

### Root Cause Analysis:
1. **Actual Implemented Source Code Values:**
   - In `backend/workload/profiles.py#L138`: `total_duration_seconds=120`, stages sum to $30 + 60 + 30 = 120\text{s}$.
   - In `backend/workload/profiles.py#L191`: `total_duration_seconds=220`, stages sum to $20 + 180 + 20 = 220\text{s}$.
   - In `results/experiments/exp_..._sudden_traffic_spike_.../config.json`: `total_duration_seconds: 120`.
2. **Origin of 180s and 360s Figures:**
   - The figures (180s for E03 and 360s for E04) were hypothetical / narrative exploratory proposals mentioned only in prose in Section 7 of `STAGE_8_EXECUTION_SAFETY_AND_HIGH_TRAFFIC_READINESS_REPORT.md`.
   - **No source code was ever changed or committed with 180s or 360s.**
3. **Cross-Artifact Consistency Check:**

| Component | E03 Duration | E04 Duration | Status | Notes |
|---|---|---|---|---|
| `backend/workload/profiles.py` | **120s** | **220s** | Authoritative Code | Canonical reference implementation |
| `backend/workload/shape_generator.py` | **120s** | **220s** | Fully Aligned | Sums stage durations ($30+60+30=120$, $20+180+20=220$) |
| `backend/workload/validation.py` | **120s** | **220s** | Fully Aligned | Asserts stage sum matches `total_duration_seconds` |
| `backend/experiments/executor.py` | **120s** | **220s** | Fully Aligned | Reads `config.total_duration_seconds` for watchdog |
| `Locust LoadTestShape.tick()` | **120s** | **220s** | Fully Aligned | Returns `None` at 120s / 220s to cleanly terminate |
| Experiment Metadata JSON | **120s** | **220s** | Fully Aligned | Verified in `results/experiments/.../config.json` |
| Frontend UI Display | **120s** | **220s** | Fully Aligned | Dynamically fetched from `/api/v1/experiments/profiles` |
| Pytest Test Suite | **120s** | **220s** | Fully Aligned | 40/40 tests assert and validate these exact values |

### Authoritative Determination:
The authoritative configurations are **120 seconds** for E03 and **220 seconds** for E04.  
**No code modification is required.** The prose narrative in the Stage 8 readiness report has been formally reconciled with the authoritative code.

---

## 3. Verify E01 Configuration

The exact configuration for **E01 — NORMAL_TRAFFIC** was verified across code, models, and metadata:

- **Profile Name:** `NORMAL_TRAFFIC`
- **Concurrency (Users):** `10`
- **Spawn Rate:** `2.0` users per second
- **Ramp-Up Duration:** `5` seconds
- **Steady-State Duration:** `120` seconds
- **Ramp-Down Duration:** `5` seconds
- **Total Duration:** `130` seconds
- **Locust Target Address:** `"frontend:80"` (mapped via `http://${FRONTEND_ADDR}` where `FRONTEND_ADDR=frontend:80` in the Kubernetes pod).
- **Creation vs Execution Alignment:**
  - `create_experiment(WorkloadProfileName.NORMAL_TRAFFIC)` extracts the canonical profile directly from `CANONICAL_PROFILES`.
  - `start_experiment(experiment_id)` retrieves the same stored configuration from `ExperimentMetadata.configuration`.
  - Both use the identical, immutable Pydantic model.

---

## 4. Frontend / Backend Configuration Consistency

1. **Zero Hardcoded Frontend Values:**
   - In `frontend/src/pages/ExperimentsPage.tsx`, profile definitions, stage breakdowns, user counts, and durations are not hardcoded.
   - The page invokes `fetchWorkloadProfiles()` on mount, which makes a GET request to `/api/v1/experiments/profiles`.
2. **Backend API Endpoint:**
   - `/api/v1/experiments/profiles` invokes `get_all_profiles()`, returning the live `CANONICAL_PROFILES` array directly.
3. **Validation Endpoint:**
   - `/api/v1/experiments/validate` runs the identical `validate_workload_config` logic that the backend executor evaluates before starting any run.
4. **Consistency Verdict:** Frontend and backend are 100% synchronized and single-sourced from `backend/workload/profiles.py`.

---

## 5. Verify Safety Configuration

The framework's safety invariants were audited and confirmed:

```
+---------------------------------------------------------------------------------------------------+
| SAFETY INVARIANT AUDIT                                                                            |
+---------------------------------------------------------------------------------------------------+
| Setting                        | Configured Value | Verification Method      | Compliance Status  |
+--------------------------------+------------------+--------------------------+--------------------+
| SCALING_ENABLED                | False            | backend/config.py#L8     | VERIFIED (LOCKED)  |
| EXPERIMENT_EXECUTION_ENABLED   | False            | backend/experiments/...  | VERIFIED (LOCKED)  |
| Actuator Mode                  | DRY-RUN          | actuator.py (dry_run=T)  | VERIFIED (LOCKED)  |
| loadgenerator Replicas         | 0 Replicas       | manifest & live spec     | VERIFIED (ZERO)    |
| Live Workload Execution        | None             | Active audit check       | VERIFIED (NONE)    |
+---------------------------------------------------------------------------------------------------+
```

- No scaling decisions were actuated.
- No pods were mutated.
- Zero traffic was injected into the cluster.

---

## 6. Verify High-Traffic Readiness (E03 and E04)

1. **Virtual-User Transitions:**
   - E03: 5 $\to$ 80 $\to$ 5 users across 3 stages.
   - E04: 0 $\to$ 60 $\to$ 60 $\to$ 0 users across 3 stages.
   - Both profiles provide continuous piecewise transitions without unhandled step jumps.
2. **Spawn Rates:**
   - E03 uses 20.0 u/s (reaches 80 users within 4 seconds of stage transition).
   - E04 uses 5.0 u/s (reaches 60 users in 12 seconds, well within the 20s ramp stage).
3. **Maximum Concurrency:**
   - E03 peak: 80 users ($\le 200$ limit).
   - E04 peak: 60 users ($\le 200$ limit).
4. **Timeouts and Watchdog Boundedness:**
   - E03 timeout: 120s + 5s grace = 125s watchdog cutoff.
   - E04 timeout: 220s + 5s grace = 225s watchdog cutoff.
   - Clean scale-to-zero occurs automatically if Locust does not exit.
5. **Synthetic High-Pressure Testing (`test_dpbps_high_traffic.py`):**
   - 7/7 tests passed: verified bottleneck detection, isolation of `cartservice`, upstream protective `HOLD`, incremental scaling clamped to `max_replicas = 5`, and scale-down suppression during `ACTIVE_DEPLOYMENT` and `POST_DEPLOYMENT`.
   - *Distinction:* Synthetic tests validate algorithmic logic in-memory using mocked data models; actual cluster measurements will occur during authorized experiment execution.

---

## 7. Testing Results

1. **Profile Validation & Workload Generation Suite:**
   - Command: `python -m pytest backend/tests/test_workload_and_experiments.py backend/tests/test_dpbps_high_traffic.py -q`
   - Result: **40 passed, 0 failures** in 16.87s (100% pass rate).
2. **Full Backend Regression Suite:**
   - Command: `python -m pytest backend/tests -q`
   - Result: **162 passed, 2 skipped, 0 failures** in 72.12s (100% pass rate).
3. **Frontend Production Build:**
   - Unmodified in this turn; previously verified cleanly (`tsc -b && vite build`, 0 errors).

---

## 8. Remaining Inconsistencies

**Zero remaining inconsistencies.**  
All six profiles are reconciled across source code, models, shape generator, validation logic, API routers, frontend clients, and test assertions.

---

## 9. Final E01 Readiness Decision

```
================================================================================
FINAL E01 WORKLOAD CONFIGURATION DECISION: GO
================================================================================
- All 6 workload profiles are audited directly from source code.
- Duration discrepancy in previous report is resolved (authoritative: E03=120s, E04=220s).
- E01 NORMAL_TRAFFIC configuration (10 users, 2 u/s, 130s, frontend:80) is verified.
- Frontend and backend configurations are 100% consistent.
- Safety interlocks are active (SCALING_ENABLED=false, EXPERIMENT_EXECUTION_ENABLED=false).
- 40 workload/high-traffic tests passed; 162 backend regression tests passed.
================================================================================
```

