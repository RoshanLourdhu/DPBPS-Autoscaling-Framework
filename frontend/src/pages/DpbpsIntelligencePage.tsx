// src/pages/DpbpsIntelligencePage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  fetchPipelineEvaluation,
  triggerPipelineEvaluation,
  fetchScalingStatus,
  updateDeploymentPhase,
  fetchControllerStatus,
  startContinuousController,
  stopContinuousController,
  setControllerInterval,
  DEPLOYMENT_PHASES,
} from "../services/api";
import type {
  PipelineEvaluationResponse,
  PipelineServiceResult,
  ScalingStatusResponse,
  ContinuousControllerStatus,
  DeploymentPhase,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  Brain,
  Cpu,
  ShieldCheck,
  Zap,
  Layers,
  Activity,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Lock,
  Search,
  CheckCircle2,
  Sliders,
  ChevronRight,
  Sparkles,
  Play,
  Square,
  Timer,
  Repeat,
} from "lucide-react";

// Pipeline stage metadata definition
interface PipelineStepInfo {
  step: number;
  name: string;
  badge: string;
  shortDesc: string;
  formula: string;
  inputs: string[];
  logic: string;
  outputs: string[];
  safety: string;
}

const PIPELINE_STEPS: PipelineStepInfo[] = [
  {
    step: 1,
    name: "Telemetry Ingestion",
    badge: "Prometheus & cAdvisor",
    shortDesc: "Polls Prometheus every cycle for container CPU, memory working set, RPS, and P95 latency.",
    formula: "U_cpu = rate(container_cpu_usage_seconds_total[2m]) / limit_cores",
    inputs: [
      "container_cpu_usage_seconds_total",
      "container_memory_working_set_bytes",
      "istio_requests_total (or envoy metrics)",
      "istio_request_duration_milliseconds_bucket",
    ],
    logic:
      "Fetches multi-dimensional metrics for all 10 microservices in the online-boutique namespace. Flags any service missing vital metrics as INSUFFICIENT_TELEMETRY.",
    outputs: ["Normalized CPU utilization (%)", "Memory utilization (%)", "Throughput (req/s)", "P95 latency (ms)"],
    safety: "Fails closed: missing telemetry prevents erroneous scaling and flags warning to operators.",
  },
  {
    step: 2,
    name: "Topology & Critical Path",
    badge: "10 Services • 14 Edges",
    shortDesc: "Traverses directed call graph to identify convergence nodes, upstream callers, and blast radius.",
    formula: "G = (V, E), \\quad |V|=10, \\quad |E|=14",
    inputs: [
      "Directed call graph: frontend -> {cart, productcatalog, ...}",
      "checkoutservice -> {cart, payment, shipping, email, currency}",
      "Critical bottleneck convergence: productcatalogservice (3 callers)",
    ],
    logic:
      "Performs topological sort and blast-radius calculation. Identifies dependency bottlenecks that could cascade into upstream user-facing latency spikes.",
    outputs: ["Caller-callee dependency mapping", "Blast radius score", "Convergence node classification"],
    safety: "Prevents upstream over-scaling when downstream bottleneck is saturated.",
  },
  {
    step: 3,
    name: "Bottleneck Detection",
    badge: "Severity Classifier",
    shortDesc: "Evaluates multi-factor pressure scores against SLA thresholds (P95 latency <= 500ms, CPU <= 70%).",
    formula: "Score(s) = w_u \\cdot (U_{cpu} / 0.70) + w_l \\cdot (L_{p95} / 500) + w_q \\cdot Q_{depth}",
    inputs: [
      "Observed CPU utilization vs target (70%)",
      "Observed P95 latency vs SLA (500 ms)",
      "Inbound concurrency and queue backlog",
    ],
    logic:
      "Classifies service severity into BOTTLENECK, UNDER_PRESSURE, HEALTHY, or INSUFFICIENT_TELEMETRY. Selects system primary bottleneck service.",
    outputs: ["Primary bottleneck service", "Per-service severity classifications", "SLA violation flags"],
    safety: "Differentiates root-cause resource exhaustion from downstream symptom latency.",
  },
  {
    step: 4,
    name: "Deployment Phase Modulation",
    badge: "Phase Weights",
    shortDesc: "Modulates scaling thresholds and suppressions based on the cluster deployment lifecycle.",
    formula: "w_{phase} \\in \\{1.0, 1.25, 1.5, 1.1\\}, \\quad \\text{SuppressDown} = (Phase == \\text{\"ACTIVE\\_DEPLOYMENT\"})",
    inputs: [
      "Active deployment phase: NORMAL_OPERATION | PRE_DEPLOYMENT | ACTIVE_DEPLOYMENT | POST_DEPLOYMENT",
      "Deployment rollout progress / pod readiness",
    ],
    logic:
      "Applies phase-specific scaling multipliers. In ACTIVE_DEPLOYMENT, scale-down requests are strictly suppressed (desired_change = 0) to avoid pod churn during rollouts.",
    outputs: ["Phase weight factor w_phase", "Scale-down suppression mask", "Phase-adjusted sensitivity"],
    safety: "Strict scale-down suppression during ACTIVE_DEPLOYMENT guarantees rolling rollout stability.",
  },
  {
    step: 5,
    name: "Target Replica Estimation",
    badge: "Proportional Scaling",
    shortDesc: "Computes raw replica demand required to bring observed utilization back to equilibrium.",
    formula: "R_{raw} = \\lceil R_{current} \\cdot (U_{obs} / U_{target}) \\cdot w_{phase} + \\lambda_{bottleneck} \\rceil",
    inputs: [
      "Current replica count (R_current)",
      "Observed utilization (U_obs)",
      "Target utilization threshold (U_target = 0.70)",
      "Phase weight (w_phase)",
      "Bottleneck priority bonus (\\lambda_{bottleneck})",
    ],
    logic:
      "Calculates proportional resource demand. If service is identified as a bottleneck, an additional priority bonus is applied to clear queueing backlogs.",
    outputs: ["Raw target replica count R_raw", "Proportional adjustment delta", "Direction of change"],
    safety: "Conservative ceiling rounding ensures headroom without excessive provisioning.",
  },
  {
    step: 6,
    name: "Safety Invariant Clamping",
    badge: "K8s Invariants",
    shortDesc: "Enforces min/max replica boundaries [1, 10], single-step limits (|ΔR| <= 2), and cooldown windows.",
    formula: "R_{clamped} = \\min(\\max(R_{raw}, R_{min}), R_{max}), \\quad |\\Delta R| \\le 2",
    inputs: [
      "R_min = 1, R_max = 10",
      "Max scale step = 2 replicas per evaluation cycle",
      "Cooldown timers: scale_up_window (60s), scale_down_stabilization (60s)",
    ],
    logic:
      "Clamps proposed replicas strictly between min and max bounds. Restricts rate of change to +/- 2 pods per cycle. Enforces cooldown dampening on scale-downs.",
    outputs: ["Bounded proposed replica count", "Action classification: SCALE_UP | SCALE_DOWN | HOLD"],
    safety: "Mathematical guarantee: pod count cannot breach cluster quotas or oscillate wildly.",
  },
  {
    step: 7,
    name: "Explainability Synthesis",
    badge: "Transparent Reasoning",
    shortDesc: "Generates deterministic natural language and mathematical justification for every decision.",
    formula: "\\text{Reason} = f(Service, Phase, Severity, Telemetry, Action, SafetyClamps)",
    inputs: [
      "All intermediate stage calculations",
      "Active deployment phase",
      "Identified bottleneck context",
      "Safety clamping state",
    ],
    logic:
      "Constructs human-auditable and machine-verifiable explanation strings. Logs explicit arithmetic derivation for operator inspection.",
    outputs: ["Structured explainable reason string", "Decision derivation record", "Audit trail timestamp"],
    safety: "Complete transparency: zero black-box decisions.",
  },
  {
    step: 8,
    name: "Actuator Safety & DRY_RUN",
    badge: "Zero-Mutation Gate",
    shortDesc: "Verifies actuator safety flags and executes decisions in DRY_RUN mode without live pod mutations.",
    formula: "\\text{ExecuteMutation} = (\\text{SCALING\\_ENABLED} == \\text{true}) \\land (\\text{DRY\\_RUN} == \\text{false})",
    inputs: [
      "SCALING_ENABLED = false (Hard safety posture)",
      "DRY_RUN = True",
      "Cluster connection status",
    ],
    logic:
      "Inspects safety posture. In DRY_RUN mode, skips kubectl / client-go patch requests, verifies what would have been applied, and records simulated execution in the actuator history.",
    outputs: ["Execution status: SIMULATED (DRY_RUN)", "cluster_modified = false", "Actuator audit history record"],
    safety: "Zero live mutations executed. Production workloads remain strictly isolated.",
  },
];

// Phase behavior matrix definitions
const PHASE_BEHAVIOR_DATA = [
  {
    dimension: "Scale-Up Aggressiveness",
    normal: "Standard threshold (70% CPU, w=1.0)",
    pre: "Proactive ramp-up (60% CPU, w=1.25)",
    active: "High urgency on bottlenecks (w=1.5)",
    post: "Equilibrium monitoring (w=1.1)",
  },
  {
    dimension: "Scale-Down Policy",
    normal: "Standard dampening (300s window)",
    pre: "Conservative hold; delays downscaling",
    active: "STRICTLY SUPPRESSED (ΔR = 0)",
    post: "Extended cooldown stabilization (60s)",
  },
  {
    dimension: "Bottleneck Prioritization",
    normal: "Standard priority across services",
    pre: "Pre-scales upstream & downstream deps",
    active: "Critical-path priority bonus (λ = +1)",
    post: "Monitors residual latency pressure",
  },
  {
    dimension: "Rolling Update Safety",
    normal: "Standard pod lifecycle management",
    pre: "Caches primed, connections established",
    active: "Zero scale-down churn during rollouts",
    post: "Stabilization verification before contraction",
  },
  {
    dimension: "Actuation Objective",
    normal: "Cost-performance equilibrium",
    pre: "Capacity headroom preparation",
    active: "Zero downtime during rollout",
    post: "Safe settling to steady-state capacity",
  },
];

export default function DpbpsIntelligencePage() {
  const [pipeline, setPipeline] = useState<PipelineEvaluationResponse | null>(null);
  const [scalingStatus, setScalingStatus] = useState<ScalingStatusResponse | null>(null);
  const [controllerStatus, setControllerStatus] = useState<ContinuousControllerStatus | null>(null);
  const [selectedService, setSelectedService] = useState<PipelineServiceResult | null>(null);
  const [selectedStepIndex, setSelectedStepIndex] = useState<number>(0);
  const [decisionFilter, setDecisionFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [phaseChanging, setPhaseChanging] = useState<boolean>(false);
  const [togglingController, setTogglingController] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [pipeData, statusData, ctrlData] = await Promise.all([
        fetchPipelineEvaluation(),
        fetchScalingStatus().catch(() => null),
        fetchControllerStatus().catch(() => null),
      ]);
      setPipeline(pipeData);
      setScalingStatus(statusData);
      setControllerStatus(ctrlData);

      // Preserve currently selected service or default to first
      setSelectedService((prev) => {
        if (!prev && pipeData.services.length > 0) {
          return pipeData.services[0];
        }
        if (prev) {
          const matched = pipeData.services.find((s) => s.service_name === prev.service_name);
          return matched || (pipeData.services.length > 0 ? pipeData.services[0] : null);
        }
        return null;
      });

      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load DPBPS algorithmic pipeline state");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleToggleController = async () => {
    setTogglingController(true);
    try {
      if (controllerStatus?.is_running) {
        await stopContinuousController();
      } else {
        await startContinuousController();
      }
      const updated = await fetchControllerStatus().catch(() => null);
      setControllerStatus(updated);
    } catch (e: any) {
      setError(`Failed to toggle continuous controller: ${e.message}`);
    } finally {
      setTogglingController(false);
    }
  };

  const handleIntervalChange = async (newSec: number) => {
    try {
      await setControllerInterval(newSec);
      const updated = await fetchControllerStatus().catch(() => null);
      setControllerStatus(updated);
    } catch (e: any) {
      setError(`Failed to set interval: ${e.message}`);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleManualEvaluation = async () => {
    setEvaluating(true);
    try {
      const updated = await triggerPipelineEvaluation();
      setPipeline(updated);
      if (updated.services.length > 0) {
        setSelectedService((prev) => {
          if (!prev) return updated.services[0];
          const matched = updated.services.find((s) => s.service_name === prev.service_name);
          return matched || updated.services[0];
        });
      }
    } catch (e: any) {
      setError(`Evaluation execution failed: ${e.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  const handlePhaseChange = async (phase: DeploymentPhase) => {
    setPhaseChanging(true);
    try {
      await updateDeploymentPhase(phase);
      await loadData();
    } catch (e: any) {
      setError(`Failed to update deployment phase: ${e.message}`);
    } finally {
      setPhaseChanging(false);
    }
  };

  // Filtered services
  const filteredServices = useMemo(() => {
    if (!pipeline?.services) return [];
    return pipeline.services.filter((svc) => {
      // Decision filter
      if (decisionFilter !== "ALL") {
        if (decisionFilter === "INSUFFICIENT_TELEMETRY") {
          if (svc.telemetry_complete) return false;
        } else if (svc.dpbps_decision !== decisionFilter) {
          return false;
        }
      }

      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = svc.service_name.toLowerCase().includes(q);
        const matchesDecision = svc.dpbps_decision.toLowerCase().includes(q);
        const matchesReason = svc.reason?.toLowerCase().includes(q);
        const matchesPhase = svc.deployment_phase?.toLowerCase().includes(q);
        if (!matchesName && !matchesDecision && !matchesReason && !matchesPhase) {
          return false;
        }
      }

      return true;
    });
  }, [pipeline, decisionFilter, searchQuery]);

  // Active step details
  const currentStep = PIPELINE_STEPS[selectedStepIndex] || PIPELINE_STEPS[0];
  const activePhase = pipeline?.deployment_phase || "NORMAL_OPERATION";

  if (loading && !pipeline) {
    return <LoadingState message="Executing DPBPS algorithmic pipeline..." />;
  }

  if (error && !pipeline) {
    return <ErrorState message={error} onRetry={loadData} />;
  }

  return (
    <div className="space-y-8 pb-12">
      {/* 1. Header & Actions */}
      <PageHeader
        title="DPBPS Intelligence Center"
        subtitle="Explainable deployment-phase-aware bottleneck-prioritized scaling engine with deterministic Kubernetes invariants."
        badge={
          <StatusBadge
            status={`EXECUTION: ${pipeline?.execution_mode || "DRY_RUN"}`}
            variant="amber"
          />
        }
        actions={
          <div className="flex items-center space-x-2">
            <button
              onClick={loadData}
              disabled={evaluating || phaseChanging}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-canvas-card border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-700 transition-colors disabled:opacity-50"
              title="Refresh telemetry & pipeline state"
            >
              <RefreshCw size={13} className={evaluating ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>
            <button
              onClick={handleManualEvaluation}
              disabled={evaluating || phaseChanging}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 transition-all hover:shadow-glow disabled:opacity-50"
            >
              <Zap size={14} className={evaluating ? "animate-pulse" : ""} />
              <span>{evaluating ? "Evaluating Pipeline..." : "Trigger Decision Cycle"}</span>
            </button>
          </div>
        }
      />

      {/* Actuator Posture Banner */}
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <ShieldCheck size={18} />
          </div>
          <div>
            <div className="font-semibold text-amber-400 flex items-center space-x-2">
              <span>Read-Only Safety Guard: Live Actuation Disabled</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 border border-amber-500/30 font-mono">
                SCALING_ENABLED=false
              </span>
            </div>
            <div className="text-text-muted mt-0.5">
              DPBPS enforces strict dry-run guarantees. Evaluated scaling actions are validated against Kubernetes invariants without modifying cluster state.
            </div>
          </div>
        </div>
        <div className="flex items-center space-x-2 shrink-0 font-mono text-[11px]">
          <span className="px-2 py-1 rounded bg-canvas-dark border border-canvas-border text-emerald-400 flex items-center space-x-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span>
            <span>Cluster Safe</span>
          </span>
          <span className="px-2 py-1 rounded bg-canvas-dark border border-canvas-border text-text-secondary">
            Mutations: <strong className="text-text-primary">0</strong>
          </span>
        </div>
      </div>

      {/* Continuous Controller Execution Engine Panel */}
      <div className="rounded-xl border border-cyan-500/30 bg-gradient-to-r from-cyan-950/20 via-canvas-card to-blue-950/20 p-5 shadow-lg shadow-cyan-500/5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                <Repeat size={16} />
              </div>
              <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider flex items-center space-x-2">
                <span>Continuous Closed-Loop DPBPS Controller</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono border font-semibold flex items-center space-x-1.5 bg-canvas-dark">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      controllerStatus?.is_running
                        ? "bg-emerald-400 animate-pulse"
                        : "bg-slate-500"
                    }`}
                  ></span>
                  <span className={controllerStatus?.is_running ? "text-emerald-400" : "text-text-muted"}>
                    {controllerStatus?.is_running ? "ACTIVE CONTINUOUS LOOP" : "STANDBY (MANUAL ONLY)"}
                  </span>
                </span>
              </h2>
            </div>
            <p className="text-xs text-text-muted">
              Autonomous telemetry ingestion, invariant validation, bottleneck prioritization, and simulated actuation in DRY_RUN mode.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center space-x-1 text-xs bg-canvas-dark border border-canvas-border rounded-lg px-2.5 py-1 text-text-muted">
              <Timer size={13} className="text-cyan-400" />
              <span>Interval:</span>
              <select
                value={controllerStatus?.interval_seconds ?? 15}
                onChange={(e) => handleIntervalChange(Number(e.target.value))}
                className="bg-transparent text-text-primary font-mono font-semibold focus:outline-none cursor-pointer pl-1"
                title="Evaluation cadence"
              >
                <option value={5} className="bg-canvas-card text-text-primary">5s</option>
                <option value={10} className="bg-canvas-card text-text-primary">10s</option>
                <option value={15} className="bg-canvas-card text-text-primary">15s</option>
                <option value={30} className="bg-canvas-card text-text-primary">30s</option>
                <option value={60} className="bg-canvas-card text-text-primary">60s</option>
              </select>
            </div>

            <button
              onClick={handleToggleController}
              disabled={togglingController}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                controllerStatus?.is_running
                  ? "bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border-rose-500/30"
                  : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30 hover:shadow-glow"
              } disabled:opacity-50`}
            >
              {controllerStatus?.is_running ? (
                <>
                  <Square size={13} />
                  <span>{togglingController ? "Stopping..." : "Stop Loop"}</span>
                </>
              ) : (
                <>
                  <Play size={13} />
                  <span>{togglingController ? "Starting..." : "Start Loop"}</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Controller Subsystem Diagnostic Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-4 pt-4 border-t border-canvas-border/50 text-xs">
          <div className="p-2.5 rounded-lg bg-canvas-dark/60 border border-canvas-border/50">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">Evaluation Cycles</div>
            <div className="text-sm font-mono font-bold text-cyan-400 mt-0.5">
              #{controllerStatus?.cycle_count ?? 0}
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-canvas-dark/60 border border-canvas-border/50">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">Last Evaluation</div>
            <div className="text-xs font-mono text-text-primary mt-0.5 truncate" title={controllerStatus?.last_evaluation_time || "Pending"}>
              {controllerStatus?.last_evaluation_time
                ? new Date(controllerStatus.last_evaluation_time).toLocaleTimeString()
                : "Awaiting cycle"}
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-canvas-dark/60 border border-canvas-border/50">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">Next Evaluation</div>
            <div className="text-xs font-mono text-text-secondary mt-0.5 truncate" title={controllerStatus?.next_evaluation_time || "Standby"}>
              {controllerStatus?.next_evaluation_time
                ? new Date(controllerStatus.next_evaluation_time).toLocaleTimeString()
                : "Manual trigger"}
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-canvas-dark/60 border border-canvas-border/50">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">Execution Latency</div>
            <div className="text-xs font-mono text-emerald-400 mt-0.5">
              {controllerStatus?.last_evaluation_duration_ms != null
                ? `${controllerStatus.last_evaluation_duration_ms.toFixed(1)} ms`
                : "—"}
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-canvas-dark/60 border border-canvas-border/50">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">Active Bottleneck</div>
            <div className="text-xs font-mono font-semibold text-amber-400 mt-0.5 truncate" title={controllerStatus?.current_bottleneck || "None"}>
              {controllerStatus?.current_bottleneck || pipeline?.bottleneck_service || "None (Equilibrium)"}
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-canvas-dark/60 border border-canvas-border/50">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">Audit History</div>
            <div className="text-xs font-mono text-text-secondary mt-0.5">
              {controllerStatus?.total_decisions_recorded ?? 0} records
            </div>
          </div>
        </div>
      </div>

      {/* 2. Section: Algorithm Overview & Deployment Phase Context */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <SectionHeader
            title="Algorithm Overview & Deployment Phase Context"
            subtitle="DPBPS dynamically modulates scaling sensitivity and suppression rules across 4 canonical lifecycle phases"
            icon={Layers}
          />
          <div className="flex items-center space-x-2 text-xs text-text-muted font-mono">
            <span>Active Phase:</span>
            <span className="px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-400 font-bold">
              {activePhase}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {DEPLOYMENT_PHASES.map((p) => {
            const isActive = activePhase === p.id;
            return (
              <div
                key={p.id}
                className={`relative rounded-xl p-4 transition-all duration-200 border ${
                  isActive
                    ? "bg-purple-950/20 border-purple-500/60 shadow-lg shadow-purple-500/10 ring-1 ring-purple-500/40"
                    : "bg-canvas-card border-canvas-border hover:border-slate-700"
                }`}
              >
                {isActive && (
                  <div className="absolute top-3 right-3 flex items-center space-x-1 px-2 py-0.5 rounded-full bg-purple-500/20 border border-purple-500/40 text-[10px] font-bold text-purple-300 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse"></span>
                    <span>ACTIVE</span>
                  </div>
                )}

                <div className="flex items-center space-x-2 mb-2">
                  <div
                    className={`p-1.5 rounded-lg border ${
                      isActive
                        ? "bg-purple-500/20 border-purple-500/40 text-purple-400"
                        : "bg-canvas-dark border-canvas-border text-text-muted"
                    }`}
                  >
                    <Layers size={14} />
                  </div>
                  <h4 className="font-bold text-sm text-text-primary">{p.label}</h4>
                </div>

                <div className="font-mono text-[10px] text-text-muted uppercase tracking-wider mb-2">
                  {p.id}
                </div>

                <p className="text-xs text-text-secondary leading-relaxed mb-4 min-h-[48px]">
                  {p.desc}
                </p>

                {/* Phase Policy Details */}
                <div className="space-y-1.5 pt-3 border-t border-canvas-border text-[11px] font-mono">
                  <div className="flex justify-between items-center text-text-muted">
                    <span>Scale-Up Weight:</span>
                    <span className="text-text-primary font-bold">
                      {p.id === "NORMAL_OPERATION" && "w = 1.0 (baseline)"}
                      {p.id === "PRE_DEPLOYMENT" && "w = 1.25 (proactive)"}
                      {p.id === "ACTIVE_DEPLOYMENT" && "w = 1.50 (urgent)"}
                      {p.id === "POST_DEPLOYMENT" && "w = 1.10 (cooldown)"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-text-muted">
                    <span>Scale-Down:</span>
                    <span
                      className={`font-bold ${
                        p.id === "ACTIVE_DEPLOYMENT" ? "text-rose-400" : "text-emerald-400"
                      }`}
                    >
                      {p.id === "ACTIVE_DEPLOYMENT" ? "SUPPRESSED (ΔR=0)" : "Standard Cooldown"}
                    </span>
                  </div>
                </div>

                {/* Action button */}
                <div className="mt-4 pt-2">
                  <button
                    onClick={() => handlePhaseChange(p.id)}
                    disabled={isActive || phaseChanging}
                    className={`w-full py-1.5 px-3 rounded-lg text-xs font-semibold transition-all ${
                      isActive
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 cursor-default"
                        : "bg-canvas-dark border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-600 disabled:opacity-40"
                    }`}
                  >
                    {isActive ? "Currently Applied" : phaseChanging ? "Switching..." : `Select ${p.label}`}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Section: Interactive Decision Pipeline Visualization */}
      <div className="space-y-4">
        <SectionHeader
          title="Interactive Algorithmic Decision Pipeline"
          subtitle="Click any step in the 8-stage decision pipeline to inspect its mathematical formulas, parameters, and invariants"
          icon={Brain}
        />

        {/* Pipeline steps scrollable grid / sequence */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {PIPELINE_STEPS.map((s, idx) => {
            const isSelected = selectedStepIndex === idx;
            return (
              <button
                key={s.step}
                onClick={() => setSelectedStepIndex(idx)}
                className={`relative flex flex-col items-start p-3 rounded-xl border text-left transition-all duration-150 ${
                  isSelected
                    ? "bg-cyan-950/20 border-cyan-500 shadow-md shadow-cyan-500/10 ring-1 ring-cyan-500/50"
                    : "bg-canvas-card border-canvas-border hover:border-slate-700 hover:bg-canvas-card/80"
                }`}
              >
                <div className="flex items-center justify-between w-full mb-1.5">
                  <span
                    className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded ${
                      isSelected
                        ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                        : "bg-canvas-dark text-text-muted border border-canvas-border"
                    }`}
                  >
                    STEP {s.step}
                  </span>
                  {idx < PIPELINE_STEPS.length - 1 && (
                    <ArrowRight size={12} className="text-text-muted opacity-40 hidden lg:block" />
                  )}
                </div>

                <div className="font-bold text-xs text-text-primary line-clamp-1">{s.name}</div>
                <div className="text-[10px] text-text-muted mt-1 line-clamp-1">{s.badge}</div>

                {isSelected && (
                  <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-cyan-400 rotate-45 rounded-xs" />
                )}
              </button>
            );
          })}
        </div>

        {/* Step Detail Drawer / Inspector */}
        <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-canvas-border gap-2">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 font-mono text-sm font-bold">
                STAGE 0{currentStep.step}
              </div>
              <div>
                <h3 className="text-base font-bold text-text-primary flex items-center space-x-2">
                  <span>{currentStep.name}</span>
                  <span className="text-xs font-mono font-normal text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
                    {currentStep.badge}
                  </span>
                </h3>
                <p className="text-xs text-text-secondary mt-0.5">{currentStep.shortDesc}</p>
              </div>
            </div>
            <div className="text-xs text-text-muted font-mono flex items-center space-x-1.5">
              <span>Step {currentStep.step} of 8</span>
              <span className="text-slate-600">•</span>
              <button
                onClick={() => setSelectedStepIndex((prev) => (prev + 1) % PIPELINE_STEPS.length)}
                className="text-cyan-400 hover:text-cyan-300 font-semibold flex items-center space-x-0.5"
              >
                <span>Next Stage</span>
                <ChevronRight size={13} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left: Mathematical Formulation & Logic */}
            <div className="space-y-3">
              <div className="rounded-lg bg-canvas-dark border border-canvas-border p-3.5 space-y-1.5">
                <div className="text-[11px] font-mono text-text-muted uppercase tracking-wider flex items-center space-x-1.5">
                  <Sliders size={13} className="text-cyan-400" />
                  <span>Mathematical Invariant / Formulation</span>
                </div>
                <div className="font-mono text-xs text-cyan-300 bg-canvas-card/80 p-2.5 rounded border border-cyan-500/20 overflow-x-auto">
                  {currentStep.formula}
                </div>
              </div>

              <div className="rounded-lg bg-canvas-dark border border-canvas-border p-3.5 space-y-1.5">
                <div className="text-[11px] font-mono text-text-muted uppercase tracking-wider flex items-center space-x-1.5">
                  <Activity size={13} className="text-cyan-400" />
                  <span>Algorithmic Processing Logic</span>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed font-sans">
                  {currentStep.logic}
                </p>
              </div>
            </div>

            {/* Right: Inputs, Outputs & Safety Guarantee */}
            <div className="space-y-3">
              <div className="rounded-lg bg-canvas-dark border border-canvas-border p-3.5 space-y-2">
                <div className="text-[11px] font-mono text-text-muted uppercase tracking-wider">
                  Inputs & Dependencies:
                </div>
                <ul className="space-y-1 font-mono text-xs text-text-secondary">
                  {currentStep.inputs.map((inp, i) => (
                    <li key={i} className="flex items-start space-x-2">
                      <span className="text-cyan-400 font-bold">›</span>
                      <span>{inp}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-lg bg-canvas-dark border border-canvas-border p-3.5 space-y-2">
                <div className="text-[11px] font-mono text-text-muted uppercase tracking-wider">
                  Outputs Produced:
                </div>
                <ul className="space-y-1 font-mono text-xs text-text-secondary">
                  {currentStep.outputs.map((out, i) => (
                    <li key={i} className="flex items-start space-x-2">
                      <span className="text-emerald-400 font-bold">✓</span>
                      <span>{out}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3 space-y-1">
                <div className="text-[10px] font-mono text-emerald-400 uppercase tracking-wider flex items-center space-x-1.5 font-bold">
                  <ShieldCheck size={13} />
                  <span>Safety Invariant Guarantee</span>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed font-sans">
                  {currentStep.safety}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Section: Decision Distribution Grid */}
      <div className="space-y-3">
        <SectionHeader
          title="Decision Distribution & Pipeline Telemetry"
          subtitle="Real-time distribution of scaling recommendations generated across all monitored microservices"
          icon={Activity}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Scale-Up Urgency"
            value={pipeline?.scale_up_count ?? 0}
            unit="services"
            variant="rose"
            icon={TrendingUp}
            subtext="Bottleneck prioritized"
          />
          <MetricCard
            title="Scale-Down Cooldown"
            value={pipeline?.scale_down_count ?? 0}
            unit="services"
            variant="amber"
            icon={TrendingDown}
            subtext={
              activePhase === "ACTIVE_DEPLOYMENT"
                ? "Scale-down suppressed"
                : "Conservative dampening"
            }
          />
          <MetricCard
            title="Equilibrium Holds"
            value={pipeline?.hold_count ?? 0}
            unit="services"
            variant="emerald"
            icon={ShieldCheck}
            subtext="Within target bounds"
          />
          <MetricCard
            title="Telemetry Coverage"
            value={`${pipeline?.complete_telemetry_services ?? 0} / ${pipeline?.total_services ?? 10}`}
            unit="complete"
            variant="cyan"
            icon={CheckCircle2}
            subtext={
              (pipeline?.incomplete_telemetry_services ?? 0) > 0
                ? `${pipeline?.incomplete_telemetry_services} with partial signals`
                : "100% metrics ingested"
            }
          />
        </div>

        {/* Sub-status bar */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono text-xs">
          <div className="p-3 rounded-xl bg-canvas-card border border-canvas-border flex items-center justify-between">
            <span className="text-text-muted">Primary System Bottleneck:</span>
            <span className="font-bold text-rose-400">
              {pipeline?.bottleneck_service || "None Detected (Balanced)"}
            </span>
          </div>
          <div className="p-3 rounded-xl bg-canvas-card border border-canvas-border flex items-center justify-between">
            <span className="text-text-muted">Actuator Invariant Mode:</span>
            <span className="font-bold text-amber-400">
              {scalingStatus?.dry_run !== false ? "DRY_RUN (Zero Mutation)" : "ACTIVE"}
            </span>
          </div>
          <div className="p-3 rounded-xl bg-canvas-card border border-canvas-border flex items-center justify-between">
            <span className="text-text-muted">Replica Bounds Enforcement:</span>
            <span className="font-bold text-cyan-400">
              [{scalingStatus?.config.min_replicas ?? 1}, {scalingStatus?.config.max_replicas ?? 10}] (Δ ≤ 2)
            </span>
          </div>
        </div>
      </div>

      {/* 5. Section: Service Decision Matrix (Explainability Table) */}
      <div className="space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <SectionHeader
            title="Service Decision Matrix & Explainability Table"
            subtitle="Click any microservice row to inspect its exact mathematical derivation and input snapshot"
            icon={Cpu}
          />

          {/* Filter Pills and Search */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Search services or decisions..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 rounded-lg text-xs bg-canvas-dark border border-canvas-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-cyan-500 w-48 sm:w-56"
              />
            </div>

            <div className="flex items-center space-x-1 bg-canvas-dark p-0.5 rounded-lg border border-canvas-border text-xs">
              {(["ALL", "SCALE_UP", "SCALE_DOWN", "HOLD", "INSUFFICIENT_TELEMETRY"] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setDecisionFilter(filter)}
                  className={`px-2 py-1 rounded-md font-mono text-[11px] transition-colors ${
                    decisionFilter === filter
                      ? "bg-canvas-card text-text-primary font-bold shadow-xs border border-canvas-border"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Matrix Table */}
        <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                  <th className="py-3 px-4 font-semibold">Microservice</th>
                  <th className="py-3 px-3 font-semibold text-center">Phase</th>
                  <th className="py-3 px-3 font-semibold text-center">Bottleneck Status</th>
                  <th className="py-3 px-3 font-semibold text-right">CPU</th>
                  <th className="py-3 px-3 font-semibold text-right">Latency P95</th>
                  <th className="py-3 px-3 font-semibold text-right">RPS</th>
                  <th className="py-3 px-3 font-semibold text-center">Replicas (Cur → Prop)</th>
                  <th className="py-3 px-3 font-semibold text-center">Decision</th>
                  <th className="py-3 px-3 font-semibold text-center">Actuator</th>
                  <th className="py-3 px-4 font-semibold">Explainable Reasoning</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-canvas-border">
                {filteredServices.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="py-8 text-center text-text-muted">
                      No microservices match the current filters.
                    </td>
                  </tr>
                ) : (
                  filteredServices.map((svc) => {
                    const isSelected = selectedService?.service_name === svc.service_name;
                    const cpuPercent =
                      svc.cpu_utilization != null ? svc.cpu_utilization * 100 : undefined;
                    const hasInsufficient = !svc.telemetry_complete;

                    return (
                      <tr
                        key={svc.service_name}
                        onClick={() => setSelectedService(svc)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-cyan-950/20 border-l-2 border-l-cyan-400"
                            : "hover:bg-canvas-dark/40"
                        }`}
                      >
                        {/* Service name */}
                        <td className="py-3 px-4 font-bold text-text-primary">
                          <div className="flex items-center space-x-2">
                            <span>{svc.service_name}</span>
                            {svc.service_name === pipeline?.bottleneck_service && (
                              <span className="px-1.5 py-0.2 rounded text-[9px] bg-rose-500/20 border border-rose-500/40 text-rose-300 font-mono font-bold">
                                BOTTLENECK
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Phase */}
                        <td className="py-3 px-3 text-center">
                          <StatusBadge
                            status={svc.deployment_phase || activePhase}
                            variant="purple"
                            size="xs"
                          />
                        </td>

                        {/* Bottleneck Status */}
                        <td className="py-3 px-3 text-center">
                          {hasInsufficient ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                              INSUFFICIENT
                            </span>
                          ) : svc.service_name === pipeline?.bottleneck_service ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-500/10 text-rose-400 border border-rose-500/30 font-bold">
                              BOTTLENECK
                            </span>
                          ) : cpuPercent && cpuPercent > 50 ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-400 border border-amber-500/30">
                              PRESSURE
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                              HEALTHY
                            </span>
                          )}
                        </td>

                        {/* CPU */}
                        <td className="py-3 px-3 text-right font-mono">
                          {cpuPercent != null ? (
                            <span
                              className={
                                cpuPercent >= 70
                                  ? "text-rose-400 font-bold"
                                  : cpuPercent >= 50
                                  ? "text-amber-400"
                                  : "text-text-primary"
                              }
                            >
                              {cpuPercent.toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-text-muted">N/A</span>
                          )}
                        </td>

                        {/* Latency P95 */}
                        <td className="py-3 px-3 text-right font-mono">
                          {svc.p95_latency != null ? (
                            <span
                              className={
                                svc.p95_latency >= 500
                                  ? "text-rose-400 font-bold"
                                  : "text-text-primary"
                              }
                            >
                              {svc.p95_latency.toFixed(1)} ms
                            </span>
                          ) : (
                            <span className="text-text-muted">N/A</span>
                          )}
                        </td>

                        {/* RPS */}
                        <td className="py-3 px-3 text-right font-mono text-text-primary">
                          {svc.request_rate != null
                            ? `${svc.request_rate.toFixed(1)}/s`
                            : "N/A"}
                        </td>

                        {/* Replicas (Cur -> Prop) */}
                        <td className="py-3 px-3 text-center font-mono">
                          <span className="font-bold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
                            {svc.current_replicas} &rarr; {svc.proposed_replica_count}
                          </span>
                        </td>

                        {/* Algorithmic Decision */}
                        <td className="py-3 px-3 text-center">
                          <StatusBadge
                            status={svc.dpbps_decision}
                            variant={
                              svc.dpbps_decision === "SCALE_UP"
                                ? "rose"
                                : svc.dpbps_decision === "SCALE_DOWN"
                                ? "amber"
                                : "emerald"
                            }
                            size="xs"
                          />
                        </td>

                        {/* Actuator Status */}
                        <td className="py-3 px-3 text-center font-mono text-[10px]">
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                            {svc.actuator_execution_status || "SIMULATED"}
                          </span>
                        </td>

                        {/* Reason */}
                        <td className="py-3 px-4 text-text-secondary truncate max-w-xs text-[11px]" title={svc.reason}>
                          {svc.reason}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 6. Section: Detailed Algorithmic Derivation Inspector */}
      {selectedService && (
        <div className="space-y-3">
          <SectionHeader
            title={`Mathematical Derivation Inspector: ${selectedService.service_name}`}
            subtitle="Step-by-step arithmetic substitution and Kubernetes invariant verification for the selected microservice"
            icon={Sparkles}
          />

          <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-5">
            {/* Inspector Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-canvas-border gap-2">
              <div className="flex items-center space-x-3">
                <span className="text-lg font-bold text-text-primary">
                  {selectedService.service_name}
                </span>
                <StatusBadge
                  status={selectedService.dpbps_decision}
                  variant={
                    selectedService.dpbps_decision === "SCALE_UP"
                      ? "rose"
                      : selectedService.dpbps_decision === "SCALE_DOWN"
                      ? "amber"
                      : "emerald"
                  }
                />
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-purple-500/10 border border-purple-500/30 text-purple-300">
                  {selectedService.deployment_phase || activePhase}
                </span>
              </div>
              <div className="flex items-center space-x-2 text-xs font-mono text-text-muted">
                <span>Evaluated:</span>
                <span className="text-text-primary">
                  {new Date(selectedService.timestamp).toLocaleTimeString()}
                </span>
                <span className="text-slate-600">•</span>
                <span className="text-amber-400 font-semibold">DRY_RUN (Unmodified)</span>
              </div>
            </div>

            {/* Arithmetic Formula Breakdown Card */}
            <div className="rounded-lg bg-canvas-dark border border-canvas-border p-4 space-y-3">
              <div className="text-xs font-mono font-semibold text-text-muted uppercase tracking-wider flex items-center space-x-2">
                <Sliders size={14} className="text-cyan-400" />
                <span>Deterministic Formulation Breakdown</span>
              </div>

              <div className="p-3 rounded bg-canvas-card border border-cyan-500/20 font-mono text-xs text-cyan-300">
                {"R_target = min(max(ceil(R_current × (U_obs / U_target) × w_phase + λ_bottleneck), R_min), R_max)"}
              </div>

              {/* Step arithmetic substitution grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-xs font-mono">
                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border">
                  <div className="text-text-muted text-[10px]">R_current</div>
                  <div className="text-sm font-bold text-text-primary mt-0.5">
                    {selectedService.current_replicas} pods
                  </div>
                </div>

                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border">
                  <div className="text-text-muted text-[10px]">U_obs / U_target</div>
                  <div className="text-sm font-bold text-text-primary mt-0.5">
                    {selectedService.cpu_utilization != null
                      ? `${(selectedService.cpu_utilization * 100).toFixed(1)}% / 70%`
                      : "N/A"}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border">
                  <div className="text-text-muted text-[10px]">w_phase</div>
                  <div className="text-sm font-bold text-purple-300 mt-0.5">
                    {selectedService.deployment_phase === "ACTIVE_DEPLOYMENT"
                      ? "1.50"
                      : selectedService.deployment_phase === "PRE_DEPLOYMENT"
                      ? "1.25"
                      : selectedService.deployment_phase === "POST_DEPLOYMENT"
                      ? "1.10"
                      : "1.00"}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border">
                  <div className="text-text-muted text-[10px]">λ_bottleneck</div>
                  <div className="text-sm font-bold text-rose-400 mt-0.5">
                    {selectedService.service_name === pipeline?.bottleneck_service ? "+1" : "0"}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border">
                  <div className="text-text-muted text-[10px]">Clamp Limits</div>
                  <div className="text-sm font-bold text-cyan-400 mt-0.5">
                    [1, 10], Δ ≤ 2
                  </div>
                </div>

                <div className="p-2.5 rounded bg-canvas-card border border-cyan-500/30">
                  <div className="text-cyan-400 text-[10px]">R_proposed</div>
                  <div className="text-sm font-bold text-cyan-300 mt-0.5">
                    {selectedService.proposed_replica_count} pods
                  </div>
                </div>
              </div>
            </div>

            {/* Telemetry Snapshot Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">OBSERVED CPU</div>
                <div className="text-sm font-bold text-text-primary mt-1">
                  {selectedService.cpu_utilization != null
                    ? `${(selectedService.cpu_utilization * 100).toFixed(1)}%`
                    : "N/A"}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Target: 70.0%</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">P95 LATENCY</div>
                <div className="text-sm font-bold text-text-primary mt-1">
                  {selectedService.p95_latency != null
                    ? `${selectedService.p95_latency.toFixed(1)} ms`
                    : "N/A"}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">SLA: &le; 500 ms</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">REQUEST THROUGHPUT</div>
                <div className="text-sm font-bold text-text-primary mt-1">
                  {selectedService.request_rate != null
                    ? `${selectedService.request_rate.toFixed(1)} req/s`
                    : "N/A"}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Telemetry Ingested</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">REPLICA TARGET</div>
                <div className="text-sm font-bold text-cyan-400 mt-1">
                  {selectedService.current_replicas} &rarr; {selectedService.proposed_replica_count}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">
                  Change: {selectedService.proposed_replica_count - selectedService.current_replicas} pods
                </div>
              </div>
            </div>

            {/* Explainable Reasoning Block */}
            <div className="p-4 rounded-lg bg-canvas-dark/60 border border-canvas-border text-xs space-y-2">
              <div className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider flex items-center space-x-1.5 font-mono">
                <Brain size={13} className="text-cyan-400" />
                <span>Controller Natural Language Reasoning:</span>
              </div>
              <p className="text-text-secondary leading-relaxed font-sans text-sm">
                {selectedService.reason}
              </p>
            </div>

            {/* Actuator Invariant Verification Block */}
            <div className="rounded-lg bg-canvas-dark border border-canvas-border p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="flex items-center space-x-2">
                <Lock size={15} className="text-amber-400 shrink-0" />
                <span className="text-text-secondary">
                  Actuator Safety Guard: <strong>{selectedService.actuator_execution_status}</strong>. Cluster state was <strong>NOT modified</strong>.
                </span>
              </div>
              <div className="flex items-center space-x-2 shrink-0 font-mono text-[11px]">
                <span className="text-text-muted">Telemetry Status:</span>
                <span
                  className={
                    selectedService.telemetry_complete
                      ? "text-emerald-400 font-bold"
                      : "text-amber-400 font-bold"
                  }
                >
                  {selectedService.telemetry_complete ? "Complete" : "Incomplete Signals"}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 7. Section: Deployment-Aware Behavior Matrix */}
      <div className="space-y-4">
        <SectionHeader
          title="Deployment-Aware Behavior Matrix"
          subtitle="Systematic policy comparison across the four canonical DPBPS lifecycle phases"
          icon={Sliders}
        />

        <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                  <th className="py-3 px-4 font-semibold">Scaling Dimension</th>
                  <th className="py-3 px-3 font-semibold">Normal Operation</th>
                  <th className="py-3 px-3 font-semibold">Pre-Deployment</th>
                  <th className="py-3 px-3 font-semibold">Active Deployment</th>
                  <th className="py-3 px-3 font-semibold">Post-Deployment</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-canvas-border">
                {PHASE_BEHAVIOR_DATA.map((row, idx) => (
                  <tr key={idx} className="hover:bg-canvas-dark/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-text-primary font-mono text-[11px]">
                      {row.dimension}
                    </td>
                    <td className="py-3 px-3 text-text-secondary">{row.normal}</td>
                    <td className="py-3 px-3 text-text-secondary">{row.pre}</td>
                    <td className="py-3 px-3 text-text-primary font-medium bg-purple-950/10">
                      {row.active}
                    </td>
                    <td className="py-3 px-3 text-text-secondary">{row.post}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
