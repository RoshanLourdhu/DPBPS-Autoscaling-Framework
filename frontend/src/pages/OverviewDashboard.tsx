// src/pages/OverviewDashboard.tsx
import { useEffect, useState, useCallback } from "react";
import {
  fetchHealth,
  fetchPipelineEvaluation,
  triggerPipelineEvaluation,
  updateDeploymentPhase,
} from "../services/api";
import type {
  HealthResponse,
  PipelineEvaluationResponse,
  PipelineServiceResult,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  RefreshCw,
  ShieldCheck,
  Server,
  Activity,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle2,
} from "lucide-react";

export default function OverviewDashboard() {
  const [pipelineData, setPipelineData] = useState<PipelineEvaluationResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [selectedPhase, setSelectedPhase] = useState<string>("NORMAL_OPERATION");
  const [phaseUpdating, setPhaseUpdating] = useState<boolean>(false);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  const loadData = useCallback(async (isManual: boolean = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [h, pipe] = await Promise.all([
        fetchHealth(),
        fetchPipelineEvaluation(),
      ]);
      setHealth(h);
      setPipelineData(pipe);
      setSelectedPhase(pipe.deployment_phase);
      setLastRefreshed(new Date().toLocaleTimeString());
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to communicate with DPBPS backend.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Controlled auto-refresh (10s interval)
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadData(false);
    }, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadData]);

  const handleManualRefresh = () => {
    loadData(true);
  };

  const handleTriggerEvaluation = async () => {
    setRefreshing(true);
    try {
      const updated = await triggerPipelineEvaluation();
      setPipelineData(updated);
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (e: any) {
      setError(`Evaluation failed: ${e.message}`);
    } finally {
      setRefreshing(false);
    }
  };

  const handlePhaseChange = async (newPhase: string) => {
    setPhaseUpdating(true);
    try {
      await updateDeploymentPhase(newPhase);
      setSelectedPhase(newPhase);
      await loadData(false);
    } catch (e: any) {
      setError(`Phase update failed: ${e.message}`);
    } finally {
      setPhaseUpdating(false);
    }
  };

  if (loading) return <LoadingState />;
  if (error && !pipelineData) return <ErrorState message={error} />;

  // Aggregated Summary Statistics
  const totalServices = pipelineData?.total_services ?? 0;
  const completeCount = pipelineData?.complete_telemetry_services ?? 0;
  const incompleteCount = pipelineData?.incomplete_telemetry_services ?? 0;
  const totalReplicas = pipelineData?.services.reduce((acc, s) => acc + s.ready_replicas, 0) ?? 0;
  const scaleUpCount = pipelineData?.scale_up_count ?? 0;
  const scaleDownCount = pipelineData?.scale_down_count ?? 0;
  const holdCount = pipelineData?.hold_count ?? 0;
  const bottleneckService = pipelineData?.bottleneck_service;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Top Banner: Strict Dry-Run Safety Notice */}
      <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <ShieldCheck className="h-6 w-6 text-amber-600 flex-shrink-0" />
          <div>
            <h3 className="text-sm font-bold text-amber-900 tracking-wide uppercase">
              Actuator Operational Mode: DRY-RUN (Zero Cluster Mutations)
            </h3>
            <p className="text-xs text-amber-700">
              Live scaling is strictly guarded (<code className="font-mono bg-amber-100 px-1 rounded">SCALING_ENABLED=false</code>). 
              All proposed replica adjustments are simulated and validated without modifying Kubernetes Deployments.
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2 text-xs">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-medium bg-green-100 text-green-800">
            Backend: {health?.status ?? "ok"}
          </span>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-medium bg-blue-100 text-blue-800">
            K8s: docker-desktop
          </span>
        </div>
      </div>

      {/* Header with Refresh Controls */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <PageHeader
          title="DPBPS Pipeline Dashboard"
          subtitle="Deployment-Phase-Aware Bottleneck-Prioritized Scaling for Microservices"
        />
        <div className="flex items-center space-x-3">
          <div className="text-xs text-gray-500 flex items-center space-x-1">
            <Clock className="h-3.5 w-3.5" />
            <span>Updated: {lastRefreshed || "Just now"}</span>
          </div>

          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-3 py-1.5 text-xs font-medium rounded border transition-colors ${
              autoRefresh
                ? "bg-green-50 text-green-700 border-green-300 hover:bg-green-100"
                : "bg-gray-50 text-gray-600 border-gray-300 hover:bg-gray-100"
            }`}
          >
            {autoRefresh ? "Auto-Refresh: ON (10s)" : "Auto-Refresh: PAUSED"}
          </button>

          <button
            onClick={handleManualRefresh}
            disabled={refreshing}
            className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium rounded bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin text-blue-600" : ""}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={handleTriggerEvaluation}
            disabled={refreshing}
            className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium rounded bg-blue-600 text-white hover:bg-blue-700 shadow-sm disabled:opacity-50"
          >
            <span>Run Pipeline</span>
          </button>
        </div>
      </div>

      {/* SECTION E: DEPLOYMENT-PHASE MONITORING & CONTROL */}
      <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center space-x-2">
              <Layers className="h-4 w-4 text-indigo-600" />
              <span>Deployment Phase Management</span>
            </h2>
            <p className="text-xs text-gray-500">
              DPBPS scaling algorithms adapt according to the CI/CD lifecycle phase to prevent scale-down during rollouts.
            </p>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
            Active Phase: {selectedPhase}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
          {[
            { phase: "NORMAL_OPERATION", label: "Normal Operation", desc: "Bidirectional scaling with standard cooldowns" },
            { phase: "PRE_DEPLOYMENT", label: "Pre-Deployment", desc: "Warmup & pre-scale protection" },
            { phase: "ACTIVE_DEPLOYMENT", label: "Active Deployment", desc: "Scale-down strictly blocked during rollout" },
            { phase: "POST_DEPLOYMENT", label: "Post-Deployment", desc: "Stabilization window before scale-down" },
          ].map((item) => (
            <button
              key={item.phase}
              disabled={phaseUpdating}
              onClick={() => handlePhaseChange(item.phase)}
              className={`p-3 text-left rounded-lg border transition-all ${
                selectedPhase === item.phase
                  ? "bg-indigo-50 border-indigo-500 text-indigo-900 shadow-sm ring-1 ring-indigo-500"
                  : "bg-gray-50 border-gray-200 text-gray-700 hover:bg-gray-100"
              }`}
            >
              <div className="text-xs font-bold">{item.label}</div>
              <div className="text-[11px] text-gray-500 mt-1 line-clamp-2">{item.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* SECTION A: SYSTEM OVERVIEW */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard title="Monitored Services" value={totalServices} demo={false} />
        <MetricCard
          title="Telemetry Health"
          value={`${completeCount}/${totalServices}`}
          unit={incompleteCount > 0 ? `(${incompleteCount} degraded)` : "100% complete"}
          demo={false}
        />
        <MetricCard title="Total Ready Replicas" value={totalReplicas} demo={false} />
        <MetricCard
          title="Proposed Scale-Up"
          value={scaleUpCount}
          unit="services"
          demo={false}
        />
        <MetricCard
          title="Proposed Scale-Down"
          value={scaleDownCount}
          unit="services"
          demo={false}
        />
        <MetricCard
          title="Hold Decisions"
          value={holdCount}
          unit="services"
          demo={false}
        />
      </div>

      {/* SECTION C & D: BOTTLENECK & ACTUATOR DRY-RUN SUMMARY CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Bottleneck Detection Card */}
        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                Bottleneck Prioritization
              </span>
              <Activity className="h-4 w-4 text-purple-600" />
            </div>
            <div className="mt-3 flex items-baseline space-x-2">
              <span className={`text-xl font-bold ${bottleneckService ? "text-red-600" : "text-green-600"}`}>
                {bottleneckService ? bottleneckService.toUpperCase() : "NO BOTTLENECK DETECTED"}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              {bottleneckService
                ? `Downstream dependency '${bottleneckService}' exhibits high latency or errors; upstream services are held to prevent cascade.`
                : "All microservices operate within configured latency target (200ms) and error threshold (5%)."}
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
            <span>Dependency graph: 10 Online Boutique services</span>
            <span>Policy: Bottleneck-Prioritized</span>
          </div>
        </div>

        {/* Kubernetes Actuator Status Card */}
        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                Kubernetes Actuator Status
              </span>
              <Server className="h-4 w-4 text-blue-600" />
            </div>
            <div className="mt-3 flex items-center space-x-2">
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800">
                DRY-RUN MODE
              </span>
              <span className="text-xs text-gray-500">
                {pipelineData?.services.filter((s) => s.actuator_execution_status === "VALIDATED").length} validated,{" "}
                {pipelineData?.services.filter((s) => s.actuator_execution_status === "SKIPPED").length} skipped,{" "}
                {pipelineData?.services.filter((s) => s.actuator_execution_status === "REJECTED").length} rejected
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Every decision undergoes safety invariant checking: replica limits [1, 10], max delta (2),
              concurrency validation, rollout checks, and HPA conflict prevention.
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
            <span>Namespace: online-boutique</span>
            <span className="text-green-600 font-semibold flex items-center space-x-1">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>Zero Cluster Modifications</span>
            </span>
          </div>
        </div>
      </div>

      {/* SECTION B & C: SERVICE & DECISION MONITORING TABLE */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
              Microservices Real-Time Telemetry & DPBPS Scaling Decisions
            </h3>
            <p className="text-xs text-gray-500">
              Integrated from Prometheus, Kubernetes Metrics Server, and DPBPS Controller in DRY-RUN mode.
            </p>
          </div>
          <span className="text-xs font-medium text-gray-500">
            Showing {pipelineData?.services.length ?? 0} deployments
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-xs">
            <thead className="bg-gray-50 text-gray-600 font-semibold uppercase">
              <tr>
                <th scope="col" className="px-4 py-3 text-left">Service</th>
                <th scope="col" className="px-3 py-3 text-right">Request Rate</th>
                <th scope="col" className="px-3 py-3 text-right">P95 Latency</th>
                <th scope="col" className="px-3 py-3 text-right">Error Rate</th>
                <th scope="col" className="px-3 py-3 text-right">CPU Util.</th>
                <th scope="col" className="px-3 py-3 text-right">Mem Util.</th>
                <th scope="col" className="px-3 py-3 text-center">Replicas (Cur / Ready)</th>
                <th scope="col" className="px-3 py-3 text-center">DPBPS Action</th>
                <th scope="col" className="px-3 py-3 text-center">Proposed Reps</th>
                <th scope="col" className="px-3 py-3 text-center">Actuator Status</th>
                <th scope="col" className="px-4 py-3 text-left">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {pipelineData?.services.map((svc: PipelineServiceResult) => {
                const isScaleUp = svc.dpbps_decision === "SCALE_UP";
                const isScaleDown = svc.dpbps_decision === "SCALE_DOWN";
                const isHold = svc.dpbps_decision === "HOLD";

                return (
                  <tr key={svc.service_name} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 whitespace-nowrap font-medium text-gray-900">
                      <div className="flex items-center space-x-1.5">
                        <span>{svc.service_name}</span>
                        {!svc.telemetry_complete && (
                          <span
                            title={`Missing metrics: ${svc.missing_metrics.join(", ")}`}
                            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-100 text-red-700"
                          >
                            Incomplete
                          </span>
                        )}
                        {svc.service_name === bottleneckService && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-700">
                            Bottleneck
                          </span>
                        )}
                      </div>
                      {svc.dependencies.length > 0 && (
                        <div className="text-[10px] text-gray-400 mt-0.5 truncate max-w-[160px]" title={`Depends on: ${svc.dependencies.join(", ")}`}>
                          Deps: {svc.dependencies.join(", ")}
                        </div>
                      )}
                    </td>

                    {/* Request Rate */}
                    <td className="px-3 py-3 whitespace-nowrap text-right font-mono">
                      {svc.request_rate !== null && svc.request_rate !== undefined ? `${svc.request_rate.toFixed(1)} req/s` : "—"}
                    </td>

                    {/* P95 Latency */}
                    <td className="px-3 py-3 whitespace-nowrap text-right font-mono">
                      {svc.p95_latency !== null && svc.p95_latency !== undefined ? `${svc.p95_latency.toFixed(1)} ms` : "—"}
                    </td>

                    {/* Error Rate */}
                    <td className="px-3 py-3 whitespace-nowrap text-right font-mono">
                      {svc.error_rate !== null && svc.error_rate !== undefined ? `${(svc.error_rate * 100).toFixed(2)}%` : "—"}
                    </td>

                    {/* CPU Utilization */}
                    <td className="px-3 py-3 whitespace-nowrap text-right font-mono">
                      {svc.cpu_utilization !== null && svc.cpu_utilization !== undefined ? (
                        <span className={svc.cpu_utilization > 0.8 ? "text-red-600 font-bold" : "text-gray-700"}>
                          {(svc.cpu_utilization * 100).toFixed(1)}%
                        </span>
                      ) : "—"}
                    </td>

                    {/* Memory Utilization */}
                    <td className="px-3 py-3 whitespace-nowrap text-right font-mono">
                      {svc.memory_utilization !== null && svc.memory_utilization !== undefined ? (
                        <span className={svc.memory_utilization > 0.8 ? "text-amber-600 font-bold" : "text-gray-700"}>
                          {(svc.memory_utilization * 100).toFixed(1)}%
                        </span>
                      ) : "—"}
                    </td>

                    {/* Replicas (Current / Ready) */}
                    <td className="px-3 py-3 whitespace-nowrap text-center font-mono">
                      <span className="font-semibold text-gray-800">{svc.current_replicas}</span>
                      <span className="text-gray-400"> / </span>
                      <span className={svc.ready_replicas === svc.current_replicas ? "text-green-600 font-semibold" : "text-amber-600 font-bold"}>
                        {svc.ready_replicas}
                      </span>
                    </td>

                    {/* DPBPS Action */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold ${
                          isScaleUp
                            ? "bg-green-100 text-green-800"
                            : isScaleDown
                            ? "bg-blue-100 text-blue-800"
                            : isHold
                            ? "bg-gray-100 text-gray-700"
                            : "bg-red-50 text-red-600"
                        }`}
                      >
                        {isScaleUp && <ArrowUpRight className="h-3 w-3 mr-0.5 text-green-700" />}
                        {isScaleDown && <ArrowDownRight className="h-3 w-3 mr-0.5 text-blue-700" />}
                        {svc.dpbps_decision}
                      </span>
                    </td>

                    {/* Proposed Replicas */}
                    <td className="px-3 py-3 whitespace-nowrap text-center font-mono">
                      <span className="font-bold text-gray-900">{svc.proposed_replica_count}</span>
                    </td>

                    {/* Actuator Status */}
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${
                          svc.actuator_execution_status === "VALIDATED"
                            ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                            : svc.actuator_execution_status === "REJECTED"
                            ? "bg-red-100 text-red-800 border border-red-200"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {svc.actuator_execution_status}
                      </span>
                    </td>

                    {/* Decision Reason */}
                    <td className="px-4 py-3 text-gray-600 max-w-xs truncate" title={svc.reason}>
                      {svc.reason}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
