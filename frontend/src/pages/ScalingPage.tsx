// src/pages/ScalingPage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  fetchScalingStatus,
  fetchScalingDecisions,
  fetchActuatorHistory,
  fetchPipelineEvaluation,
  fetchServices,
  fetchActuatorStatus,
  toggleEmergencyStop,
} from "../services/api";
import type {
  ScalingStatusResponse,
  DecisionRecord,
  ActuatorResult,
  PipelineEvaluationResponse,
  PipelineServiceResult,
  ServiceInfo,
  ActuatorStatusResponse,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { ConfirmationDialog } from "../components/ui/ConfirmationDialog";
import {
  History,
  ShieldCheck,
  RefreshCw,
  Sliders,
  Cpu,
  Search,
  Lock,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Activity,
  AlertCircle,
  AlertOctagon,
  Power,
} from "lucide-react";

interface UnifiedDecisionRow {
  id: string;
  service_name: string;
  timestamp: string;
  deployment_phase: string;
  action: string;
  current_replicas: number;
  proposed_replicas: number;
  reason: string;
  actuator_mode: string;
  execution_status: string;
  cluster_modified: boolean;
  cpu_utilization?: number;
  memory_utilization?: number;
  request_rate?: number;
  p95_latency?: number;
  bottleneck?: string;
}

export default function ScalingPage() {
  const [status, setStatus] = useState<ScalingStatusResponse | null>(null);
  const [actuatorStatus, setActuatorStatus] = useState<ActuatorStatusResponse | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [actuatorHistory, setActuatorHistory] = useState<ActuatorResult[]>([]);
  const [pipeline, setPipeline] = useState<PipelineEvaluationResponse | null>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<UnifiedDecisionRow | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [decisionFilter, setDecisionFilter] = useState<string>("ALL");
  const [phaseFilter, setPhaseFilter] = useState<string>("ALL");
  const [serviceFilter, setServiceFilter] = useState<string>("ALL");
  const [isEmergencyModalOpen, setIsEmergencyModalOpen] = useState<boolean>(false);
  const [isTogglingEmergency, setIsTogglingEmergency] = useState<boolean>(false);

  const loadData = useCallback(async (isInitial = false) => {
    try {
      const [st, actStatus, decs, act, pipe, svcs] = await Promise.all([
        fetchScalingStatus().catch(() => null),
        fetchActuatorStatus().catch(() => null),
        fetchScalingDecisions(50).catch(() => []),
        fetchActuatorHistory(50).catch(() => []),
        fetchPipelineEvaluation().catch(() => null),
        fetchServices().catch(() => []),
      ]);
      setStatus(st);
      setActuatorStatus(actStatus);
      setDecisions(decs);
      setActuatorHistory(act);
      setPipeline(pipe);
      setServices(svcs);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load scaling telemetry.");
    } finally {
      if (isInitial) setLoading(false);
    }
  }, []);

  const handleToggleEmergencyStop = async () => {
    setIsTogglingEmergency(true);
    try {
      const shouldEnable = !actuatorStatus?.emergency_stop;
      await toggleEmergencyStop(
        shouldEnable,
        shouldEnable ? "Operator manual emergency stop triggered" : "Operator restored normal scaling"
      );
      await loadData(false);
    } catch (err: any) {
      alert(`Emergency stop toggle failed: ${err.message || err}`);
    } finally {
      setIsTogglingEmergency(false);
      setIsEmergencyModalOpen(false);
    }
  };

  useEffect(() => {
    loadData(true);
    const interval = setInterval(() => loadData(false), 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Build unified chronological decision list
  const unifiedRecords: UnifiedDecisionRow[] = useMemo(() => {
    const list: UnifiedDecisionRow[] = [];

    // First include the latest evaluated pipeline results (real-time live cycle)
    if (pipeline?.services) {
      pipeline.services.forEach((p: PipelineServiceResult, idx: number) => {
        list.push({
          id: `live_${p.service_name}_${idx}`,
          service_name: p.service_name,
          timestamp: p.timestamp || pipeline.timestamp,
          deployment_phase: p.deployment_phase || pipeline.deployment_phase,
          action: p.dpbps_decision,
          current_replicas: p.current_replicas,
          proposed_replicas: p.proposed_replica_count,
          reason: p.reason,
          actuator_mode: pipeline.execution_mode || "DRY_RUN",
          execution_status: p.actuator_execution_status || "SIMULATED",
          cluster_modified: p.cluster_modified || false,
          cpu_utilization: p.cpu_utilization,
          memory_utilization: p.memory_utilization,
          request_rate: p.request_rate,
          p95_latency: p.p95_latency,
          bottleneck: p.bottleneck_information,
        });
      });
    }

    // Next merge historical decisions from controller history
    if (decisions.length > 0) {
      decisions.forEach((d: DecisionRecord, idx: number) => {
        const svcInfo = services.find((s) => s.name === d.service_name);
        list.push({
          id: `hist_${d.service_name}_${d.timestamp}_${idx}`,
          service_name: d.service_name,
          timestamp: d.timestamp,
          deployment_phase: d.phase || "NORMAL_OPERATION",
          action: d.action,
          current_replicas: d.previous_replicas,
          proposed_replicas: d.requested_replicas,
          reason: d.reason,
          actuator_mode: "DRY_RUN",
          execution_status: "SIMULATED",
          cluster_modified: false,
          cpu_utilization: svcInfo?.cpu_utilisation,
          memory_utilization: svcInfo?.memory_utilisation,
          request_rate: svcInfo?.request_rate,
          p95_latency: svcInfo?.p95_latency,
          bottleneck: d.bottleneck,
        });
      });
    }

    // Merge actuator audit logs if they have separate entries
    if (actuatorHistory.length > 0) {
      actuatorHistory.forEach((a: ActuatorResult, idx: number) => {
        // avoid exact duplicate by checking timestamp and service
        const exists = list.some(
          (r) => r.service_name === a.service_name && r.timestamp === a.timestamp
        );
        if (!exists) {
          list.push({
            id: `act_${a.service_name}_${a.timestamp}_${idx}`,
            service_name: a.service_name,
            timestamp: a.timestamp,
            deployment_phase: a.deployment_phase || "NORMAL_OPERATION",
            action: a.action,
            current_replicas: a.current_replicas,
            proposed_replicas: a.requested_replicas,
            reason: a.reason,
            actuator_mode: a.execution_mode || "DRY_RUN",
            execution_status: a.status || "SIMULATED",
            cluster_modified: a.cluster_modified || false,
          });
        }
      });
    }

    // Sort by timestamp descending
    return list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [pipeline, decisions, actuatorHistory, services]);

  // Keep selected record active
  useEffect(() => {
    if (!selectedRecord && unifiedRecords.length > 0) {
      setSelectedRecord(unifiedRecords[0]);
    } else if (selectedRecord) {
      const match = unifiedRecords.find((r) => r.id === selectedRecord.id);
      if (match) setSelectedRecord(match);
    }
  }, [unifiedRecords, selectedRecord]);

  // Filtered decisions
  const filteredRecords = useMemo(() => {
    return unifiedRecords.filter((rec) => {
      if (decisionFilter !== "ALL" && rec.action !== decisionFilter) return false;
      if (phaseFilter !== "ALL" && rec.deployment_phase !== phaseFilter) return false;
      if (serviceFilter !== "ALL" && rec.service_name !== serviceFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          rec.service_name.toLowerCase().includes(q) ||
          rec.action.toLowerCase().includes(q) ||
          rec.reason.toLowerCase().includes(q) ||
          rec.deployment_phase.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [unifiedRecords, decisionFilter, phaseFilter, serviceFilter, searchQuery]);

  // Aggregate stats across services
  const serviceAggregates = useMemo(() => {
    const map: Record<
      string,
      {
        service_name: string;
        total: number;
        scaleUp: number;
        scaleDown: number;
        hold: number;
        insufficient: number;
        currentReplicas: number;
        latestAction: string;
        latestTime: string;
      }
    > = {};

    unifiedRecords.forEach((rec) => {
      if (!map[rec.service_name]) {
        map[rec.service_name] = {
          service_name: rec.service_name,
          total: 0,
          scaleUp: 0,
          scaleDown: 0,
          hold: 0,
          insufficient: 0,
          currentReplicas: rec.current_replicas,
          latestAction: rec.action,
          latestTime: rec.timestamp,
        };
      }
      const agg = map[rec.service_name];
      agg.total += 1;
      if (rec.action === "SCALE_UP") agg.scaleUp += 1;
      else if (rec.action === "SCALE_DOWN") agg.scaleDown += 1;
      else if (rec.action === "HOLD") agg.hold += 1;
      else if (rec.action === "INSUFFICIENT_TELEMETRY") agg.insufficient += 1;
    });

    return Object.values(map);
  }, [unifiedRecords]);

  // Global counts
  const totalScaleUp = pipeline?.scale_up_count ?? unifiedRecords.filter((r) => r.action === "SCALE_UP").length;
  const totalScaleDown = pipeline?.scale_down_count ?? unifiedRecords.filter((r) => r.action === "SCALE_DOWN").length;
  const totalHold = pipeline?.hold_count ?? unifiedRecords.filter((r) => r.action === "HOLD").length;
  const totalInsufficient = unifiedRecords.filter((r) => r.action === "INSUFFICIENT_TELEMETRY").length;

  if (loading && unifiedRecords.length === 0) {
    return <LoadingState message="Loading scaling decision & actuator audit history..." />;
  }

  if (error && unifiedRecords.length === 0 && !status) {
    return <ErrorState message={error} onRetry={() => loadData(true)} />;
  }

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <PageHeader
        title="Scaling Control & Actuator History"
        subtitle="Audit trail of explainable DPBPS controller recommendations, Kubernetes safety invariants, and dry-run execution results."
        badge={
          <div className="flex items-center space-x-2">
            <StatusBadge
              status={`CONTROLLER: ${status?.controller_running ? "RUNNING" : "STANDBY"}`}
              variant={status?.controller_running ? "emerald" : "slate"}
            />
            <StatusBadge
              status={`ACTUATOR: ${status?.dry_run !== false ? "DRY_RUN (SIMULATED)" : "ACTIVE"}`}
              variant="amber"
            />
          </div>
        }
        actions={
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setIsEmergencyModalOpen(true)}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-sm ${
                actuatorStatus?.emergency_stop
                  ? "bg-emerald-600 hover:bg-emerald-500 text-white"
                  : "bg-rose-600/90 hover:bg-rose-500 text-white border border-rose-500/50"
              }`}
            >
              <Power size={13} />
              <span>{actuatorStatus?.emergency_stop ? "Deactivate E-Stop" : "Emergency Stop"}</span>
            </button>
            <button
              onClick={() => loadData(false)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-canvas-card border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-700 transition-colors"
            >
              <RefreshCw size={13} />
              <span>Refresh History</span>
            </button>
          </div>
        }
      />

      {/* Emergency Stop Active Alert Banner */}
      {actuatorStatus?.emergency_stop && (
        <div className="rounded-xl border border-rose-500/50 bg-rose-500/10 p-4 flex items-center justify-between text-xs animate-pulse">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/40 shrink-0">
              <AlertOctagon size={20} />
            </div>
            <div>
              <div className="font-bold text-rose-400 text-sm flex items-center space-x-2">
                <span>GLOBAL EMERGENCY STOP ACTIVATED</span>
                <span className="px-2 py-0.5 rounded text-[10px] bg-rose-500/30 text-rose-300 font-mono">
                  FAIL-CLOSED
                </span>
              </div>
              <p className="text-rose-200/80 mt-0.5 font-sans">
                {actuatorStatus.emergency_stop_reason || "All autoscaling operations are immediately rejected."} Any proposed scale-up or scale-down is blocked until an authorized operator deactivates this control.
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsEmergencyModalOpen(true)}
            className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-lg shrink-0 transition-colors"
          >
            Deactivate
          </button>
        </div>
      )}

      {/* Actuator Safety Posture Banner */}
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 shrink-0">
            <ShieldCheck size={18} />
          </div>
          <div>
            <div className="font-semibold text-amber-400 flex items-center space-x-2">
              <span>Actuator Safety Posture: Live Cluster Scaling Locked</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 border border-amber-500/30 font-mono">
                SCALING_ENABLED=false
              </span>
            </div>
            <p className="text-text-muted mt-0.5 leading-relaxed font-sans">
              Recommendations generated by DPBPS are evaluated and audited against cluster bounds [1, 10] and step rate limits (|ΔR| &le; 2). All actuation executes strictly in <strong>DRY_RUN</strong> simulation; zero Kubernetes scale patch mutations are executed.
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2 shrink-0 font-mono text-[11px]">
          <span className="px-2 py-1 rounded bg-canvas-dark border border-canvas-border text-emerald-400">
            Cluster Mutations: 0
          </span>
          <span className="px-2 py-1 rounded bg-canvas-dark border border-canvas-border text-text-secondary">
            Logged Events: {unifiedRecords.length}
          </span>
        </div>
      </div>

      {/* 1. Scaling Overview KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
        <MetricCard
          title="Total Decisions"
          value={unifiedRecords.length}
          unit="events"
          variant="cyan"
          icon={History}
          subtext="Audited recommendations"
        />
        <MetricCard
          title="Scale-Up Urgency"
          value={totalScaleUp}
          unit="actions"
          variant="rose"
          icon={TrendingUp}
          subtext="Bottleneck prioritized"
        />
        <MetricCard
          title="Scale-Down Actions"
          value={totalScaleDown}
          unit="actions"
          variant="amber"
          icon={TrendingDown}
          subtext="Conservative dampening"
        />
        <MetricCard
          title="Equilibrium Holds"
          value={totalHold}
          unit="cycles"
          variant="emerald"
          icon={ShieldCheck}
          subtext="Within target bounds"
        />
        <MetricCard
          title="Insufficient Telemetry"
          value={totalInsufficient}
          unit="events"
          variant="purple"
          icon={AlertCircle}
          subtext="Fails safe (hold)"
        />
        <MetricCard
          title="Cluster Mutations"
          value="0"
          unit="pods"
          variant="emerald"
          icon={Lock}
          subtext="100% DRY_RUN safe"
        />
      </div>

      {/* 2. Action Classification Legend */}
      <div className="p-3.5 rounded-xl bg-canvas-card border border-canvas-border text-xs space-y-2">
        <div className="flex items-center space-x-2 text-[11px] font-mono uppercase tracking-wider text-text-secondary font-bold">
          <Sliders size={13} className="text-cyan-400" />
          <span>Algorithmic Action Classification Taxonomy:</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 font-mono text-[11px]">
          <div className="p-2 rounded bg-canvas-dark border border-canvas-border">
            <strong className="text-rose-400">SCALE_UP:</strong> Proactive or bottleneck-prioritized capacity expansion (+1 or +2 pods).
          </div>
          <div className="p-2 rounded bg-canvas-dark border border-canvas-border">
            <strong className="text-amber-400">SCALE_DOWN:</strong> Traffic contraction recommendation (strictly suppressed during ACTIVE_DEPLOYMENT).
          </div>
          <div className="p-2 rounded bg-canvas-dark border border-canvas-border">
            <strong className="text-emerald-400">HOLD:</strong> Resource utilization equilibrium; service operating safely within target bounds.
          </div>
          <div className="p-2 rounded bg-canvas-dark border border-canvas-border">
            <strong className="text-purple-400">INSUFFICIENT_TELEMETRY:</strong> Missing metric signals; fails closed to HOLD to prevent churn.
          </div>
          <div className="p-2 rounded bg-canvas-dark border border-canvas-border">
            <strong className="text-cyan-400">SIMULATED (DRY_RUN):</strong> Verified by actuator logic; zero Kubernetes deployment modifications.
          </div>
          <div className="p-2 rounded bg-canvas-dark border border-canvas-border">
            <strong className="text-emerald-400">LIVE MUTATION:</strong> Live pod replica alteration (strictly locked in current safety mode).
          </div>
        </div>
      </div>

      {/* 3. Scaling Decision History Table */}
      <div className="space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <SectionHeader
            title="Chronological Scaling Decision & Actuator Log"
            subtitle="Click any decision row to inspect exact telemetry snapshots and mathematical derivation reasons"
            icon={History}
          />

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Search service, reason, phase..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 rounded-lg text-xs bg-canvas-dark border border-canvas-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-cyan-500 w-48 sm:w-56"
              />
            </div>

            {/* Service filter */}
            <select
              value={serviceFilter}
              onChange={(e) => setServiceFilter(e.target.value)}
              className="px-2 py-1.5 rounded-lg text-xs font-mono bg-canvas-dark border border-canvas-border text-text-primary focus:outline-none focus:border-cyan-500"
            >
              <option value="ALL">All Services</option>
              {serviceAggregates.map((s) => (
                <option key={s.service_name} value={s.service_name}>
                  {s.service_name}
                </option>
              ))}
            </select>

            {/* Phase filter */}
            <select
              value={phaseFilter}
              onChange={(e) => setPhaseFilter(e.target.value)}
              className="px-2 py-1.5 rounded-lg text-xs font-mono bg-canvas-dark border border-canvas-border text-text-primary focus:outline-none focus:border-cyan-500"
            >
              <option value="ALL">All Phases</option>
              <option value="NORMAL_OPERATION">Normal Operation</option>
              <option value="PRE_DEPLOYMENT">Pre-Deployment</option>
              <option value="ACTIVE_DEPLOYMENT">Active Deployment</option>
              <option value="POST_DEPLOYMENT">Post-Deployment</option>
            </select>

            {/* Decision filter */}
            <div className="flex items-center space-x-1 bg-canvas-dark p-0.5 rounded-lg border border-canvas-border text-xs">
              {(["ALL", "SCALE_UP", "SCALE_DOWN", "HOLD"] as const).map((filter) => (
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

        {/* History Table */}
        <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                  <th className="py-3 px-4 font-semibold">Timestamp</th>
                  <th className="py-3 px-3 font-semibold">Microservice</th>
                  <th className="py-3 px-3 font-semibold text-center">Phase</th>
                  <th className="py-3 px-3 font-semibold text-center">Replicas (Cur → Prop)</th>
                  <th className="py-3 px-3 font-semibold text-center">Action</th>
                  <th className="py-3 px-3 font-semibold text-center">Actuator Mode</th>
                  <th className="py-3 px-3 font-semibold text-center">Status</th>
                  <th className="py-3 px-4 font-semibold">Algorithmic Reasoning</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-canvas-border">
                {filteredRecords.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-text-muted">
                      No scaling decision records match the selected filters.
                    </td>
                  </tr>
                ) : (
                  filteredRecords.map((rec) => {
                    const isSelected = selectedRecord?.id === rec.id;
                    return (
                      <tr
                        key={rec.id}
                        onClick={() => setSelectedRecord(rec)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-cyan-950/20 border-l-2 border-l-cyan-400"
                            : "hover:bg-canvas-dark/30"
                        }`}
                      >
                        <td className="py-3 px-4 font-mono text-text-muted text-[11px] whitespace-nowrap">
                          {new Date(rec.timestamp).toLocaleTimeString()}
                        </td>
                        <td className="py-3 px-3 font-bold text-text-primary">
                          <div className="flex items-center space-x-1.5">
                            <Cpu size={13} className="text-text-muted" />
                            <span>{rec.service_name}</span>
                          </div>
                        </td>
                        <td className="py-3 px-3 text-center">
                          <StatusBadge status={rec.deployment_phase} variant="purple" size="xs" />
                        </td>
                        <td className="py-3 px-3 text-center font-mono">
                          <span className="font-bold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
                            {rec.current_replicas} &rarr; {rec.proposed_replicas}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-center">
                          <StatusBadge
                            status={rec.action}
                            variant={
                              rec.action === "SCALE_UP"
                                ? "rose"
                                : rec.action === "SCALE_DOWN"
                                ? "amber"
                                : "emerald"
                            }
                            size="xs"
                          />
                        </td>
                        <td className="py-3 px-3 text-center font-mono text-[10px]">
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                            {rec.actuator_mode}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-center font-mono text-[10px]">
                          <span className="px-1.5 py-0.5 rounded bg-canvas-dark border border-canvas-border text-emerald-400">
                            {rec.execution_status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-text-secondary truncate max-w-xs text-[11px]" title={rec.reason}>
                          {rec.reason}
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

      {/* 4. Decision Details & Actuator Inspector (Selected Decision) */}
      {selectedRecord && (
        <div className="space-y-4">
          <SectionHeader
            title={`Decision Details & Actuator Audit: ${selectedRecord.service_name}`}
            subtitle="Deep inspection of input telemetry, safety bounds, and controller reasoning for the selected decision event"
            icon={Sparkles}
          />

          <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-canvas-border gap-2">
              <div className="flex items-center space-x-3">
                <span className="text-base font-bold text-text-primary">
                  {selectedRecord.service_name}
                </span>
                <StatusBadge
                  status={selectedRecord.action}
                  variant={
                    selectedRecord.action === "SCALE_UP"
                      ? "rose"
                      : selectedRecord.action === "SCALE_DOWN"
                      ? "amber"
                      : "emerald"
                  }
                />
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-purple-500/10 border border-purple-500/30 text-purple-300">
                  {selectedRecord.deployment_phase}
                </span>
              </div>
              <div className="text-xs font-mono text-text-muted flex items-center space-x-2">
                <span>Timestamp:</span>
                <strong className="text-text-primary">
                  {new Date(selectedRecord.timestamp).toLocaleString()}
                </strong>
              </div>
            </div>

            {/* Telemetry Snapshot Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">CPU UTILIZATION</div>
                <div className="text-sm font-bold text-text-primary mt-1">
                  {selectedRecord.cpu_utilization != null
                    ? `${(selectedRecord.cpu_utilization * 100).toFixed(1)}%`
                    : "N/A"}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Target: 70.0%</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">MEMORY UTILIZATION</div>
                <div className="text-sm font-bold text-text-primary mt-1">
                  {selectedRecord.memory_utilization != null
                    ? `${(selectedRecord.memory_utilization * 100).toFixed(1)}%`
                    : "N/A"}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Threshold: 75.0%</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">REQUEST THROUGHPUT</div>
                <div className="text-sm font-bold text-text-primary mt-1">
                  {selectedRecord.request_rate != null
                    ? `${selectedRecord.request_rate.toFixed(1)} req/s`
                    : "N/A"}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Prometheus Ingestion</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">REPLICA TRANSITION</div>
                <div className="text-sm font-bold text-cyan-400 mt-1">
                  {selectedRecord.current_replicas} &rarr; {selectedRecord.proposed_replicas} pods
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">
                  Delta: {selectedRecord.proposed_replicas - selectedRecord.current_replicas}
                </div>
              </div>
            </div>

            {/* Explainable Reasoning */}
            <div className="p-4 rounded-lg bg-canvas-dark/60 border border-canvas-border space-y-1.5 text-xs">
              <div className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider flex items-center space-x-1.5 font-mono">
                <Activity size={13} className="text-cyan-400" />
                <span>Controller Reasoning & Algorithmic Derivation:</span>
              </div>
              <p className="text-text-secondary leading-relaxed font-sans text-sm">
                {selectedRecord.reason}
              </p>
            </div>

            {/* Actuator Invariant Verification */}
            <div className="p-3.5 rounded-lg bg-canvas-dark border border-canvas-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="flex items-center space-x-2">
                <Lock size={14} className="text-amber-400 shrink-0" />
                <span className="text-text-secondary">
                  Actuator Safety Guard: <strong>{selectedRecord.execution_status}</strong> ({selectedRecord.actuator_mode}). Cluster was <strong>NOT modified</strong>.
                </span>
              </div>
              <div className="flex items-center space-x-2 shrink-0 font-mono text-[11px]">
                <span className="text-text-muted">Replica Invariant:</span>
                <span className="text-cyan-400 font-bold">[1, 10], |ΔR| &le; 2</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 5. Service-Level Scaling Aggregates */}
      <div className="space-y-4">
        <SectionHeader
          title="Service-Level Scaling Activity Breakdown"
          subtitle="Cumulative decision distributions across each of the 10 monitored Online Boutique microservices"
          icon={Cpu}
        />

        <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                  <th className="py-3 px-4 font-semibold">Microservice</th>
                  <th className="py-3 px-3 font-semibold text-center">Current Pods</th>
                  <th className="py-3 px-3 font-semibold text-right">Total Events</th>
                  <th className="py-3 px-3 font-semibold text-right">Scale-Up</th>
                  <th className="py-3 px-3 font-semibold text-right">Scale-Down</th>
                  <th className="py-3 px-3 font-semibold text-right">Holds</th>
                  <th className="py-3 px-3 font-semibold text-center">Latest Action</th>
                  <th className="py-3 px-4 font-semibold">Latest Evaluation Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-canvas-border font-mono">
                {serviceAggregates.map((s) => (
                  <tr key={s.service_name} className="hover:bg-canvas-dark/30">
                    <td className="py-3 px-4 font-bold text-text-primary">
                      {s.service_name}
                    </td>
                    <td className="py-3 px-3 text-center text-cyan-400 font-bold">
                      {s.currentReplicas}
                    </td>
                    <td className="py-3 px-3 text-right text-text-primary">{s.total}</td>
                    <td className="py-3 px-3 text-right text-rose-400 font-bold">{s.scaleUp}</td>
                    <td className="py-3 px-3 text-right text-amber-400">{s.scaleDown}</td>
                    <td className="py-3 px-3 text-right text-emerald-400">{s.hold}</td>
                    <td className="py-3 px-3 text-center">
                      <StatusBadge
                        status={s.latestAction}
                        variant={
                          s.latestAction === "SCALE_UP"
                            ? "rose"
                            : s.latestAction === "SCALE_DOWN"
                            ? "amber"
                            : "emerald"
                        }
                        size="xs"
                      />
                    </td>
                    <td className="py-3 px-4 text-text-muted text-[11px]">
                      {new Date(s.latestTime).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Confirmation Dialog for Emergency Stop */}
      <ConfirmationDialog
        isOpen={isEmergencyModalOpen}
        title={actuatorStatus?.emergency_stop ? "Deactivate Emergency Stop?" : "Activate Global Emergency Stop?"}
        message={
          actuatorStatus?.emergency_stop
            ? "Deactivating the emergency stop will restore DPBPS actuator readiness. In simulation mode (dry_run=true), decisions will be validated again."
            : "Activating Emergency Stop provides immediate fail-closed protection: ALL dynamic scaling decisions (including dry-run validation) will be rejected immediately."
        }
        confirmText={
          actuatorStatus?.emergency_stop
            ? isTogglingEmergency ? "Restoring..." : "Restore Scaling"
            : isTogglingEmergency ? "Halting..." : "HALT ALL SCALING"
        }
        variant={actuatorStatus?.emergency_stop ? "primary" : "danger"}
        onConfirm={handleToggleEmergencyStop}
        onCancel={() => setIsEmergencyModalOpen(false)}
      />
    </div>
  );
}
