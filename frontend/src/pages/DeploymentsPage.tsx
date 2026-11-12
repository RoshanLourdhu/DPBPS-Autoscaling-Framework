// src/pages/DeploymentsPage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  fetchDeployments,
  fetchHealth,
  fetchServices,
  fetchPipelineEvaluation,
  updateDeploymentPhase,
  fetchRolloutStatus,
  fetchCicdEvents,
  reconcileDeployments,
  sendCicdWebhookEvent,
  DEPLOYMENT_PHASES,
} from "../services/api";
import type {
  DeploymentInfo,
  DeploymentPhase,
  ServiceInfo,
  PipelineEvaluationResponse,
  RolloutStatus,
  CicdEvent,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  Rocket,
  Layers,
  Sliders,
  RefreshCw,
  Activity,
  Cpu,
  Search,
  CheckCircle2,
  GitCommit,
  RotateCcw,
  Zap,
  Radio,
  X,
} from "lucide-react";


interface EnrichedDeploymentRow {
  service_name: string;
  deployment_phase: string;
  ready_replicas: number;
  desired_replicas: number;
  updated_replicas: number;
  generation: number;
  observed_generation: number;
  rollout_status: "HEALTHY" | "ROLLING_OUT" | "IDLE";
  rollout_in_progress: boolean;
  conditions: string[];
  dpbps_decision: string;
  scale_down_protection: string;
  reason?: string;
  cpu_percent?: number;
  latency_p95?: number;
}

export default function DeploymentsPage() {
  const [deployments, setDeployments] = useState<DeploymentInfo[]>([]);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [pipeline, setPipeline] = useState<PipelineEvaluationResponse | null>(null);
  const [rollouts, setRollouts] = useState<RolloutStatus[]>([]);
  const [cicdEvents, setCicdEvents] = useState<CicdEvent[]>([]);
  const [activePhase, setActivePhase] = useState<DeploymentPhase>("NORMAL_OPERATION");
  const [isUpdating, setIsUpdating] = useState(false);
  const [isReconciling, setIsReconciling] = useState(false);
  const [reconcileFeedback, setReconcileFeedback] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  // Webhook Simulator Modal State
  const [isSimulateModalOpen, setIsSimulateModalOpen] = useState(false);
  const [simService, setSimService] = useState("checkoutservice");
  const [simType, setSimType] = useState("started");
  const [isSubmittingSim, setIsSubmittingSim] = useState(false);

  const loadData = useCallback(async (isInitial = false) => {
    try {
      const [depsData, servData, pipeData, healthData, rolloutsData, cicdData] = await Promise.all([
        fetchDeployments().catch(() => []),
        fetchServices().catch(() => []),
        fetchPipelineEvaluation().catch(() => null),
        fetchHealth().catch(() => null),
        fetchRolloutStatus().catch(() => []),
        fetchCicdEvents(undefined, 25).catch(() => []),
      ]);

      setDeployments(depsData);
      setServices(servData);
      setPipeline(pipeData);
      setRollouts(rolloutsData);
      setCicdEvents(cicdData);

      if (pipeData?.deployment_phase) {
        setActivePhase(pipeData.deployment_phase as DeploymentPhase);
      } else if (healthData?.deployment_phase) {
        setActivePhase(healthData.deployment_phase as DeploymentPhase);
      }

      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load deployment lifecycle state");
    } finally {
      if (isInitial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(true);
    const interval = setInterval(() => loadData(false), 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Handle phase update via Phase Controller
  const handlePhaseChange = async (newPhase: DeploymentPhase) => {
    if (newPhase === activePhase || isUpdating) return;
    setIsUpdating(true);

    try {
      const result = await updateDeploymentPhase(newPhase);
      setActivePhase(result.phase);
      await loadData(false);
    } catch (err: any) {
      alert(`Failed to update deployment phase: ${err.message || err}`);
    } finally {
      setIsUpdating(false);
    }
  };

  // Reconcile Kubernetes rollouts
  const handleReconcile = async () => {
    setIsReconciling(true);
    setReconcileFeedback(null);
    try {
      const results = await reconcileDeployments();
      const updatedCount = results.filter((r) => r.action !== "NO_CHANGE" && r.action !== "ERROR").length;
      setReconcileFeedback(`Reconciliation completed. ${updatedCount} service(s) updated.`);
      await loadData(false);
    } catch (err: any) {
      setReconcileFeedback(`Reconciliation failed: ${err.message || err}`);
    } finally {
      setIsReconciling(false);
      setTimeout(() => setReconcileFeedback(null), 5000);
    }
  };

  // Submit simulated CI/CD webhook event
  const handleSimulateWebhook = async () => {
    setIsSubmittingSim(true);
    try {
      const eventId = `sim-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`;
      await sendCicdWebhookEvent({
        event_id: eventId,
        service_name: simService,
        event_type: simType,
        timestamp: new Date().toISOString(),
        commit_sha: "canary-sim",
        image_tag: "v1.2-sim",
        pipeline_id: "pipe-test",
      });
      setIsSimulateModalOpen(false);
      await loadData(false);
    } catch (err: any) {
      alert(`Webhook simulation failed: ${err.message || err}`);
    } finally {
      setIsSubmittingSim(false);
    }
  };

  // Build combined service deployment table
  const enrichedRows: EnrichedDeploymentRow[] = useMemo(() => {
    const baseServices = services.length > 0
      ? services.map((s) => s.name)
      : [
          "frontend",
          "cartservice",
          "productcatalogservice",
          "currencyservice",
          "paymentservice",
          "shippingservice",
          "emailservice",
          "checkoutservice",
          "recommendationservice",
          "adservice",
        ];

    return baseServices.map((name) => {
      const dep = deployments.find((d) => d.id === name);
      const svc = services.find((s) => s.name === name);
      const pipeResult = pipeline?.services.find((p) => p.service_name === name);
      const rollout = rollouts.find((r) => r.service_name === name);

      const ready = rollout?.ready_replicas ?? dep?.ready_replicas ?? svc?.ready_replicas ?? 1;
      const desired = rollout?.desired_replicas ?? svc?.desired_replicas ?? ready;
      const updated = rollout?.updated_replicas ?? desired;
      const gen = rollout?.generation ?? 1;
      const obsGen = rollout?.observed_generation ?? 1;
      const isMismatch = (gen !== obsGen) || (updated < desired) || (ready < desired && desired > 0);
      const svcPhase = rollout?.current_phase || activePhase;

      // Scale-down protection semantics based on active phase
      let protection = "Standard Elasticity (Baseline)";
      if (svcPhase === "ACTIVE_DEPLOYMENT") {
        protection = "SUPPRESSED (Zero Scale-Down During Rollout)";
      } else if (svcPhase === "POST_DEPLOYMENT") {
        protection = "STABILIZING (60s Cooldown Buffer)";
      } else if (svcPhase === "PRE_DEPLOYMENT") {
        protection = "PROACTIVE RAMP (Pre-Scaling Permitted)";
      }

      const condList = rollout?.conditions?.map((c) => c.reason || c.type) || [];

      return {
        service_name: name,
        deployment_phase: svcPhase,
        ready_replicas: ready,
        desired_replicas: desired,
        updated_replicas: updated,
        generation: gen,
        observed_generation: obsGen,
        rollout_status: isMismatch ? "ROLLING_OUT" : ready > 0 ? "HEALTHY" : "IDLE",
        rollout_in_progress: isMismatch,
        conditions: condList,
        dpbps_decision: pipeResult?.dpbps_decision || "HOLD",
        scale_down_protection: protection,
        reason: pipeResult?.reason || "Nominal steady-state operation within bounds",
        cpu_percent: svc?.cpu_utilisation !== undefined ? svc.cpu_utilisation * 100 : undefined,
        latency_p95: svc?.p95_latency,
      };
    });
  }, [services, deployments, pipeline, rollouts, activePhase]);

  // Filtered rows
  const filteredRows = useMemo(() => {
    return enrichedRows.filter((row) => {
      if (statusFilter !== "ALL" && row.rollout_status !== statusFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          row.service_name.toLowerCase().includes(q) ||
          row.dpbps_decision.toLowerCase().includes(q) ||
          row.scale_down_protection.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [enrichedRows, statusFilter, searchQuery]);

  const inFlightCount = enrichedRows.filter((r) => r.rollout_status === "ROLLING_OUT").length;

  if (loading && deployments.length === 0 && services.length === 0) {
    return <LoadingState message="Loading deployment lifecycle intelligence..." />;
  }

  if (error && deployments.length === 0 && services.length === 0) {
    return <ErrorState message={error} onRetry={() => loadData(true)} />;
  }

  return (
    <div className="space-y-8 pb-12">
      {/* Header & Primary Actions */}
      <PageHeader
        title="CI/CD Deployment Intelligence"
        subtitle="Automated Kubernetes rollout awareness, webhook event ingestion, and deployment-phase elasticity modulation."
        badge={
          <StatusBadge
            status={`GLOBAL PHASE: ${activePhase}`}
            variant="purple"
            pulse
          />
        }
        actions={
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setIsSimulateModalOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-600/30 transition-colors"
            >
              <Zap size={13} />
              <span>Simulate Webhook</span>
            </button>
            <button
              onClick={handleReconcile}
              disabled={isReconciling}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-canvas-card border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-700 transition-colors disabled:opacity-50"
            >
              <RotateCcw size={13} className={isReconciling ? "animate-spin text-cyan-400" : ""} />
              <span>{isReconciling ? "Reconciling..." : "Reconcile Rollouts"}</span>
            </button>
            <button
              onClick={() => loadData(false)}
              disabled={isUpdating}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-canvas-card border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-700 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={13} className={isUpdating ? "animate-spin text-purple-400" : ""} />
              <span>Refresh</span>
            </button>
          </div>
        }
      />

      {/* Reconciliation Feedback Alert */}
      {reconcileFeedback && (
        <div className="rounded-xl border border-cyan-500/40 bg-cyan-500/10 p-3.5 text-xs text-cyan-300 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <CheckCircle2 size={16} />
            <span>{reconcileFeedback}</span>
          </div>
          <button onClick={() => setReconcileFeedback(null)} className="text-cyan-400 hover:text-cyan-200">
            <X size={14} />
          </button>
        </div>
      )}

      {/* 1. Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Global Deployment Phase"
          value={activePhase}
          variant="purple"
          icon={Layers}
          subtext="Cluster baseline phase"
        />
        <MetricCard
          title="Monitored Microservices"
          value={enrichedRows.length}
          unit="services"
          variant="cyan"
          icon={Rocket}
          subtext="Online Boutique namespace"
        />
        <MetricCard
          title="Rollouts In Flight"
          value={inFlightCount}
          unit="updating"
          variant={inFlightCount > 0 ? "amber" : "emerald"}
          icon={Activity}
          subtext={
            inFlightCount > 0
              ? `${inFlightCount} service(s) undergoing rolling update`
              : "All 10 services at steady-state"
          }
        />
        <MetricCard
          title="CI/CD Events Logged"
          value={cicdEvents.length}
          unit="events"
          variant="slate"
          icon={Radio}
          subtext="Webhook audit trail"
        />
      </div>

      {/* 2. Section: Deployment Phase Controller */}
      <div className="space-y-4">
        <SectionHeader
          title="Deployment Lifecycle Phase Controller"
          subtitle="Modulate DPBPS scaling urgency, priority weights, and scale-down suppressions across the cluster"
          icon={Sliders}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {DEPLOYMENT_PHASES.map((p) => {
            const isSelected = activePhase === p.id;
            return (
              <div
                key={p.id}
                className={`relative rounded-xl p-4 transition-all duration-200 border flex flex-col justify-between ${
                  isSelected
                    ? "bg-purple-950/20 border-purple-500/60 shadow-lg shadow-purple-500/10 ring-1 ring-purple-500/40"
                    : "bg-canvas-card border-canvas-border hover:border-slate-700 hover:bg-canvas-card/80"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <div
                        className={`p-1.5 rounded-lg border ${
                          isSelected
                            ? "bg-purple-500/20 border-purple-500/40 text-purple-300"
                            : "bg-canvas-dark border-canvas-border text-text-muted"
                        }`}
                      >
                        <Layers size={14} />
                      </div>
                      <h4 className="font-bold text-sm text-text-primary">{p.label}</h4>
                    </div>
                    {isSelected && (
                      <span className="flex items-center space-x-1 px-2 py-0.5 rounded-full bg-purple-500/20 border border-purple-500/40 text-[10px] font-bold text-purple-300 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse"></span>
                        <span>ACTIVE</span>
                      </span>
                    )}
                  </div>

                  <div className="font-mono text-[10px] text-text-muted uppercase tracking-wider mb-2">
                    {p.id}
                  </div>

                  <p className="text-xs text-text-secondary leading-relaxed mb-4 min-h-[44px]">
                    {p.desc}
                  </p>

                  <div className="space-y-1.5 pt-3 border-t border-canvas-border text-[11px] font-mono">
                    <div className="flex justify-between items-center text-text-muted">
                      <span>Scale-Down Policy:</span>
                      <span
                        className={`font-bold ${
                          p.id === "ACTIVE_DEPLOYMENT"
                            ? "text-rose-400"
                            : p.id === "POST_DEPLOYMENT"
                            ? "text-amber-400"
                            : "text-emerald-400"
                        }`}
                      >
                        {p.id === "ACTIVE_DEPLOYMENT"
                          ? "SUPPRESSED (ΔR=0)"
                          : p.id === "POST_DEPLOYMENT"
                          ? "Stabilization Buffer"
                          : "Standard Dampening"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-canvas-border">
                  <button
                    onClick={() => handlePhaseChange(p.id)}
                    disabled={isSelected || isUpdating}
                    className={`w-full py-1.5 px-3 rounded-lg text-xs font-semibold transition-all ${
                      isSelected
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 cursor-default"
                        : "bg-canvas-dark border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-600 disabled:opacity-40"
                    }`}
                  >
                    {isSelected
                      ? "Currently Applied"
                      : isUpdating
                      ? "Applying Phase..."
                      : `Apply ${p.label}`}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Section: Service Deployment & Rollout Status Table */}
      <div className="space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <SectionHeader
            title="Microservice Rollout & Elasticity Status"
            subtitle="Live Kubernetes generation tracking, replica updates, per-service phases, and scale-down protections"
            icon={Rocket}
          />

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Search services or protection..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 rounded-lg text-xs bg-canvas-dark border border-canvas-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-cyan-500 w-48 sm:w-56"
              />
            </div>

            <div className="flex items-center space-x-1 bg-canvas-dark p-0.5 rounded-lg border border-canvas-border text-xs">
              {(["ALL", "HEALTHY", "ROLLING_OUT"] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setStatusFilter(filter)}
                  className={`px-2 py-1 rounded-md font-mono text-[11px] transition-colors ${
                    statusFilter === filter
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

        <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                  <th className="py-3 px-4 font-semibold">Microservice</th>
                  <th className="py-3 px-3 font-semibold text-center">Service Phase</th>
                  <th className="py-3 px-3 font-semibold text-center">Generation</th>
                  <th className="py-3 px-3 font-semibold text-center">Updated / Ready / Desired</th>
                  <th className="py-3 px-3 font-semibold text-center">Rollout Status</th>
                  <th className="py-3 px-3 font-semibold text-right">CPU %</th>
                  <th className="py-3 px-3 font-semibold text-right">P95 Latency</th>
                  <th className="py-3 px-3 font-semibold text-center">DPBPS Action</th>
                  <th className="py-3 px-4 font-semibold">Scale-Down Protection Posture</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-canvas-border">
                {filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-text-muted">
                      No microservices match the selected filters.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((row) => (
                    <tr key={row.service_name} className="hover:bg-canvas-dark/30 transition-colors">
                      <td className="py-3 px-4 font-bold text-text-primary">
                        <div className="flex items-center space-x-2">
                          <Cpu size={14} className="text-text-muted" />
                          <span>{row.service_name}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <StatusBadge status={row.deployment_phase} variant="purple" size="xs" />
                      </td>
                      <td className="py-3 px-3 text-center font-mono">
                        <span className={`px-2 py-0.5 rounded text-[11px] ${
                          row.generation !== row.observed_generation
                            ? "bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40"
                            : "bg-canvas-dark text-text-muted border border-canvas-border"
                        }`}>
                          {row.generation} / {row.observed_generation}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center font-mono">
                        <span className="font-bold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
                          {row.updated_replicas} / {row.ready_replicas} / {row.desired_replicas}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <StatusBadge
                          status={row.rollout_status}
                          variant={row.rollout_status === "HEALTHY" ? "emerald" : "amber"}
                          size="xs"
                        />
                      </td>
                      <td className="py-3 px-3 text-right font-mono text-text-primary">
                        {row.cpu_percent != null ? `${row.cpu_percent.toFixed(1)}%` : "N/A"}
                      </td>
                      <td className="py-3 px-3 text-right font-mono text-text-primary">
                        {row.latency_p95 != null ? `${row.latency_p95.toFixed(1)} ms` : "N/A"}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <StatusBadge
                          status={row.dpbps_decision}
                          variant={
                            row.dpbps_decision === "SCALE_UP"
                              ? "rose"
                              : row.dpbps_decision === "SCALE_DOWN"
                              ? "amber"
                              : "emerald"
                          }
                          size="xs"
                        />
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px]">
                        <span
                          className={`px-2 py-0.5 rounded border ${
                            row.deployment_phase === "ACTIVE_DEPLOYMENT"
                              ? "bg-rose-500/10 text-rose-400 border-rose-500/20 font-bold"
                              : row.deployment_phase === "POST_DEPLOYMENT"
                              ? "bg-purple-500/10 text-purple-300 border-purple-500/20"
                              : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          }`}
                        >
                          {row.scale_down_protection}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 4. Section: CI/CD Webhook Ingestion & Event Stream */}
      <div className="space-y-3">
        <SectionHeader
          title="CI/CD Ingestion Audit Stream"
          subtitle="Real-time deployment lifecycle webhooks received from CI/CD pipelines"
          icon={GitCommit}
        />

        <div className="rounded-xl border border-canvas-border bg-canvas-card p-4 shadow-card">
          {cicdEvents.length === 0 ? (
            <div className="py-8 text-center space-y-2">
              <div className="w-10 h-10 rounded-full bg-canvas-dark border border-canvas-border text-text-muted flex items-center justify-center mx-auto">
                <Radio size={18} />
              </div>
              <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider">
                No CI/CD Events Logged Yet
              </h4>
              <p className="text-xs text-text-muted max-w-md mx-auto">
                The endpoint <code className="font-mono text-cyan-400">/api/v1/cicd/events</code> is listening for HMAC-authenticated deployment webhooks. You can use the "Simulate Webhook" button above to test the integration.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-canvas-border">
              {cicdEvents.map((evt) => (
                <div key={evt.event_id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                  <div className="flex items-center space-x-3">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        evt.event_type === "started"
                          ? "bg-purple-400"
                          : evt.event_type === "succeeded"
                          ? "bg-emerald-400"
                          : "bg-rose-400"
                      }`}
                    />
                    <div className="flex items-center space-x-2 font-mono">
                      <span className="font-bold text-text-primary">{evt.service_name}</span>
                      <StatusBadge
                        status={evt.event_type.toUpperCase()}
                        variant={
                          evt.event_type === "succeeded"
                            ? "emerald"
                            : evt.event_type === "started"
                            ? "purple"
                            : "rose"
                        }
                        size="xs"
                      />
                      <span className="text-text-muted text-[11px]">
                        ({evt.previous_phase} &rarr; {evt.new_phase})
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center space-x-3 text-[11px] font-mono text-text-muted">
                    {evt.commit_sha && (
                      <span className="px-1.5 py-0.5 rounded bg-canvas-dark border border-canvas-border text-text-secondary">
                        {evt.commit_sha.substring(0, 7)}
                      </span>
                    )}
                    <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
                    <span className="text-[10px] text-text-muted opacity-60">{evt.event_id}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Webhook Simulator Modal */}
      {isSimulateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <div className="bg-canvas-card border border-canvas-border rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-canvas-border pb-3">
              <h3 className="font-bold text-sm text-text-primary flex items-center space-x-2">
                <Zap size={16} className="text-cyan-400" />
                <span>Simulate CI/CD Deployment Event</span>
              </h3>
              <button
                onClick={() => setIsSimulateModalOpen(false)}
                className="text-text-muted hover:text-text-primary"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-text-secondary mb-1">Target Microservice</label>
                <select
                  value={simService}
                  onChange={(e) => setSimService(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-canvas-dark border border-canvas-border text-text-primary"
                >
                  {enrichedRows.map((r) => (
                    <option key={r.service_name} value={r.service_name}>
                      {r.service_name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-text-secondary mb-1">Lifecycle Event Type</label>
                <select
                  value={simType}
                  onChange={(e) => setSimType(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-canvas-dark border border-canvas-border text-text-primary"
                >
                  <option value="started">started &rarr; ACTIVE_DEPLOYMENT</option>
                  <option value="progressing">progressing &rarr; ACTIVE_DEPLOYMENT</option>
                  <option value="succeeded">succeeded &rarr; POST_DEPLOYMENT</option>
                  <option value="failed">failed &rarr; NORMAL_OPERATION</option>
                  <option value="cancelled">cancelled &rarr; NORMAL_OPERATION</option>
                </select>
              </div>

              <p className="text-[11px] text-text-muted leading-relaxed">
                This triggers a simulated event payload to <code className="font-mono text-cyan-400">POST /api/v1/cicd/events</code>, updating the per-service deployment phase and verifying DPBPS elasticity modulation in safe DRY_RUN mode.
              </p>
            </div>

            <div className="flex items-center justify-end space-x-2 pt-3 border-t border-canvas-border">
              <button
                onClick={() => setIsSimulateModalOpen(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-text-secondary hover:text-text-primary"
              >
                Cancel
              </button>
              <button
                onClick={handleSimulateWebhook}
                disabled={isSubmittingSim}
                className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
              >
                {isSubmittingSim ? "Sending..." : "Dispatch Event"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
