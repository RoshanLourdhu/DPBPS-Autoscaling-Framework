// src/pages/BottleneckAnalysisPage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  fetchServices,
  fetchPipelineEvaluation,
  fetchHealth,
  triggerPipelineEvaluation,
} from "../services/api";
import type {
  ServiceInfo,
  PipelineEvaluationResponse,
  PipelineServiceResult,
  HealthResponse,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { DataTable } from "../components/ui/DataTable";
import type { ColumnDef } from "../components/ui/DataTable";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  Flame,
  AlertTriangle,
  Activity,
  ShieldCheck,
  RefreshCw,
  Zap,
  ArrowRight,
  ArrowDownRight,
  X,
  Search,
  Network,
  Layers,
  HelpCircle,
} from "lucide-react";

export type BottleneckSeverity =
  | "BOTTLENECK"
  | "UNDER_PRESSURE"
  | "HEALTHY"
  | "INSUFFICIENT_TELEMETRY";

interface EnrichedServiceRow {
  name: string;
  serviceInfo?: ServiceInfo;
  pipelineResult?: PipelineServiceResult;
  severity: BottleneckSeverity;
  readyReplicas: number;
  desiredReplicas: number;
  cpuUtilisation: number;
  memoryUtilisation: number;
  requestRate: number;
  p95Latency: number;
  errorRate: number;
  telemetryAvailable: boolean;
  decisionAction: string;
  reason: string;
  dependencies: string[];
}

export default function BottleneckAnalysisPage() {
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [pipeline, setPipeline] = useState<PipelineEvaluationResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [selectedService, setSelectedService] = useState<EnrichedServiceRow | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [severityFilter, setSeverityFilter] = useState<"ALL" | BottleneckSeverity>("ALL");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  const loadData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [svcData, pipeData, healthData] = await Promise.all([
        fetchServices(),
        fetchPipelineEvaluation(),
        fetchHealth(),
      ]);
      setServices(svcData);
      setPipeline(pipeData);
      setHealth(healthData);
      setLastRefreshed(new Date().toLocaleTimeString());
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load bottleneck diagnosis data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(false), 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleManualEvaluation = async () => {
    setEvaluating(true);
    try {
      const updated = await triggerPipelineEvaluation();
      setPipeline(updated);
      await loadData(false);
    } catch (e: any) {
      setError(`Evaluation failed: ${e.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  const bottleneckService = pipeline?.bottleneck_service;

  // Inverted Call Graph: Map each service to incoming callers
  const incomingMap = useMemo(() => {
    const map: Record<string, string[]> = {};
    services.forEach((s) => {
      (s.dependencies || []).forEach((dep) => {
        if (!map[dep]) map[dep] = [];
        if (!map[dep].includes(s.name)) {
          map[dep].push(s.name);
        }
      });
    });
    return map;
  }, [services]);

  // Combine services and pipeline results into enriched rows
  const enrichedRows = useMemo<EnrichedServiceRow[]>(() => {
    const pipeMap = new Map<string, PipelineServiceResult>();
    if (pipeline?.services) {
      pipeline.services.forEach((ps) => pipeMap.set(ps.service_name, ps));
    }

    return services.map((s) => {
      const pr = pipeMap.get(s.name);
      let severity: BottleneckSeverity = "HEALTHY";

      if (s.name === bottleneckService) {
        severity = "BOTTLENECK";
      } else if (!s.telemetry_available || pr?.dpbps_decision === "EXCLUDED") {
        severity = "INSUFFICIENT_TELEMETRY";
      } else if (
        pr?.dpbps_decision === "SCALE_UP" ||
        s.cpu_utilisation >= 0.7 ||
        s.p95_latency > 200
      ) {
        severity = "UNDER_PRESSURE";
      }

      return {
        name: s.name,
        serviceInfo: s,
        pipelineResult: pr,
        severity,
        readyReplicas: s.ready_replicas,
        desiredReplicas: s.desired_replicas ?? s.ready_replicas,
        cpuUtilisation: s.cpu_utilisation,
        memoryUtilisation: s.memory_utilisation,
        requestRate: s.request_rate,
        p95Latency: s.p95_latency,
        errorRate: s.error_rate,
        telemetryAvailable: s.telemetry_available ?? true,
        decisionAction: pr?.dpbps_decision || "HOLD",
        reason: pr?.reason || "Nominal load within configured threshold.",
        dependencies: s.dependencies || [],
      };
    });
  }, [services, pipeline, bottleneckService]);

  // Keep selected service reference fresh
  useEffect(() => {
    if (enrichedRows.length > 0) {
      if (!selectedService) {
        const defaultTarget = enrichedRows.find((r) => r.severity === "BOTTLENECK") || enrichedRows[0];
        setSelectedService(defaultTarget);
      } else {
        const updatedTarget = enrichedRows.find((r) => r.name === selectedService.name);
        if (updatedTarget) setSelectedService(updatedTarget);
      }
    }
  }, [enrichedRows, selectedService]);

  // Severity Counts
  const countBottlenecks = useMemo(
    () => enrichedRows.filter((r) => r.severity === "BOTTLENECK").length,
    [enrichedRows]
  );
  const countPressure = useMemo(
    () => enrichedRows.filter((r) => r.severity === "UNDER_PRESSURE").length,
    [enrichedRows]
  );
  const countHealthy = useMemo(
    () => enrichedRows.filter((r) => r.severity === "HEALTHY").length,
    [enrichedRows]
  );
  const countInsufficient = useMemo(
    () => enrichedRows.filter((r) => r.severity === "INSUFFICIENT_TELEMETRY").length,
    [enrichedRows]
  );

  // Filtered rows for the table
  const filteredRows = useMemo(() => {
    return enrichedRows.filter((row) => {
      if (severityFilter !== "ALL" && row.severity !== severityFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = row.name.toLowerCase().includes(q);
        const matchesDep = row.dependencies.some((d) => d.toLowerCase().includes(q));
        if (!matchesName && !matchesDep) return false;
      }
      return true;
    });
  }, [enrichedRows, severityFilter, searchQuery]);

  // Table Columns
  const columns: ColumnDef<EnrichedServiceRow>[] = [
    {
      key: "name",
      header: "Microservice",
      render: (r) => (
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-text-primary">{r.name}</span>
          {r.severity === "BOTTLENECK" && (
            <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse">
              BOTTLENECK
            </span>
          )}
        </div>
      ),
      sortable: true,
      width: "170px",
    },
    {
      key: "severity",
      header: "Severity",
      render: (r) => {
        let variant: "rose" | "amber" | "emerald" | "slate" = "emerald";
        let label = "HEALTHY";
        if (r.severity === "BOTTLENECK") {
          variant = "rose";
          label = "CRITICAL";
        } else if (r.severity === "UNDER_PRESSURE") {
          variant = "amber";
          label = "PRESSURE";
        } else if (r.severity === "INSUFFICIENT_TELEMETRY") {
          variant = "slate";
          label = "INCOMPLETE";
        }
        return <StatusBadge status={label} variant={variant} size="xs" />;
      },
      align: "center",
      sortable: true,
      width: "110px",
    },
    {
      key: "readyReplicas",
      header: "Replicas",
      render: (r) => (
        <span className="font-mono text-cyan-400 font-bold text-xs">
          {r.readyReplicas} / {r.desiredReplicas}
        </span>
      ),
      align: "center",
      sortable: true,
      width: "100px",
    },
    {
      key: "cpuUtilisation",
      header: "CPU Util.",
      render: (r) => {
        if (!r.telemetryAvailable) {
          return <span className="font-mono text-text-muted text-xs">N/A</span>;
        }
        const pct = (r.cpuUtilisation * 100).toFixed(1);
        const isHigh = r.cpuUtilisation >= 0.7;
        return (
          <div className="flex items-center space-x-2 font-mono text-xs">
            <div className="w-14 bg-canvas-dark rounded-full h-1.5 overflow-hidden border border-canvas-border">
              <div
                className={`h-full rounded-full ${isHigh ? "bg-rose-500" : "bg-cyan-400"}`}
                style={{ width: `${Math.min(100, r.cpuUtilisation * 100)}%` }}
              />
            </div>
            <span className={isHigh ? "text-rose-400 font-bold" : "text-text-primary"}>
              {pct}%
            </span>
          </div>
        );
      },
      align: "left",
      sortable: true,
      width: "130px",
    },
    {
      key: "memoryUtilisation",
      header: "Memory Util.",
      render: (r) => {
        if (!r.telemetryAvailable) {
          return <span className="font-mono text-text-muted text-xs">N/A</span>;
        }
        const pct = (r.memoryUtilisation * 100).toFixed(1);
        return (
          <div className="flex items-center space-x-2 font-mono text-xs">
            <div className="w-14 bg-canvas-dark rounded-full h-1.5 overflow-hidden border border-canvas-border">
              <div
                className="h-full rounded-full bg-blue-400"
                style={{ width: `${Math.min(100, r.memoryUtilisation * 100)}%` }}
              />
            </div>
            <span className="text-text-primary">{pct}%</span>
          </div>
        );
      },
      align: "left",
      sortable: true,
      width: "130px",
    },
    {
      key: "requestRate",
      header: "Throughput",
      render: (r) => {
        if (!r.telemetryAvailable) {
          return <span className="font-mono text-text-muted text-xs">N/A</span>;
        }
        return (
          <span className="font-mono text-xs text-text-primary font-bold">
            {r.requestRate.toFixed(1)}{" "}
            <span className="text-text-muted text-[10px] font-normal">req/s</span>
          </span>
        );
      },
      align: "right",
      sortable: true,
      width: "115px",
    },
    {
      key: "p95Latency",
      header: "P95 Latency",
      render: (r) => {
        if (!r.telemetryAvailable) {
          return <span className="font-mono text-text-muted text-xs">N/A</span>;
        }
        const isSlaBreached = r.p95Latency > 200;
        return (
          <span className={`font-mono text-xs font-bold ${isSlaBreached ? "text-rose-400" : "text-text-primary"}`}>
            {r.p95Latency.toFixed(1)}{" "}
            <span className="text-text-muted text-[10px] font-normal">ms</span>
          </span>
        );
      },
      align: "right",
      sortable: true,
      width: "115px",
    },
    {
      key: "errorRate",
      header: "Error Rate",
      render: (r) => {
        if (!r.telemetryAvailable) {
          return <span className="font-mono text-text-muted text-xs">N/A</span>;
        }
        return (
          <span className="font-mono text-xs text-text-muted">
            {(r.errorRate * 100).toFixed(2)}%
          </span>
        );
      },
      align: "right",
      sortable: true,
      width: "95px",
    },
    {
      key: "decisionAction",
      header: "DPBPS Action",
      render: (r) => (
        <StatusBadge
          status={r.decisionAction}
          variant={
            r.decisionAction === "SCALE_UP"
              ? "rose"
              : r.decisionAction === "SCALE_DOWN"
              ? "amber"
              : r.decisionAction === "EXCLUDED"
              ? "slate"
              : "emerald"
          }
          size="xs"
        />
      ),
      align: "center",
      sortable: true,
      width: "120px",
    },
  ];

  if (loading) return <LoadingState message="Aggregating bottleneck diagnostic metrics..." />;
  if (error && services.length === 0) return <ErrorState message={error} onRetry={() => loadData(true)} />;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Bottleneck Diagnosis & Prioritization"
        subtitle="Autonomous detection of critical-path microservice saturation, downstream latency amplification, and elasticity prioritization across the Online Boutique call-graph."
        badge={
          <StatusBadge
            status={bottleneckService ? `CRITICAL: ${bottleneckService}` : "NO ACTIVE BOTTLENECK"}
            variant={bottleneckService ? "rose" : "emerald"}
            pulse={!!bottleneckService}
          />
        }
        actions={
          <div className="flex items-center space-x-2">
            <button
              onClick={handleManualEvaluation}
              disabled={evaluating}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 transition-colors disabled:opacity-50"
            >
              <Zap size={14} className={evaluating ? "animate-pulse" : ""} />
              <span>{evaluating ? "Evaluating..." : "Run Decision Cycle"}</span>
            </button>
            <button
              onClick={() => loadData(true)}
              disabled={refreshing}
              className="p-1.5 rounded-lg border border-canvas-border bg-canvas-card hover:bg-canvas-hover text-text-secondary hover:text-text-primary disabled:opacity-50 transition-colors"
              title={`Last refreshed: ${lastRefreshed}`}
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin text-cyan-400" : ""} />
            </button>
          </div>
        }
      />

      {/* Safety Notice & Actuator Invariant Banner */}
      <div className="bg-canvas-card border-l-4 border-l-amber-500 border border-canvas-border p-4 rounded-xl shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-start sm:items-center space-x-3">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 flex-shrink-0">
            <ShieldCheck size={20} />
          </div>
          <div>
            <div className="text-xs font-semibold text-text-primary flex items-center space-x-2">
              <span>Operating Posture: DRY-RUN Mode Active</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-400 font-bold">
                SCALING_ENABLED=false
              </span>
            </div>
            <p className="text-[11px] text-text-secondary mt-0.5 leading-relaxed">
              All bottleneck scaling recommendations are calculated by the DPBPS controller in dry-run simulation. Kubernetes cluster pods remain protected with zero write mutations.
            </p>
          </div>
        </div>
        <Link
          to="/scaling"
          className="flex items-center space-x-1 text-xs text-amber-400 hover:text-amber-300 font-medium whitespace-nowrap self-end sm:self-center"
        >
          <span>Actuator Audit Log</span>
          <ArrowRight size={12} />
        </Link>
      </div>

      {/* Section A: Bottleneck Overview KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <MetricCard
          title="Monitored Services"
          value={services.length}
          unit="active"
          variant="cyan"
          icon={Activity}
          subtext="Online Boutique"
          to="/services"
        />
        <MetricCard
          title="Identified Bottlenecks"
          value={countBottlenecks}
          unit="critical"
          variant={countBottlenecks > 0 ? "rose" : "emerald"}
          icon={Flame}
          subtext={countBottlenecks > 0 ? "Scale priority 1" : "Zero bottlenecks"}
        />
        <MetricCard
          title="Services Under Pressure"
          value={countPressure}
          unit="warning"
          variant={countPressure > 0 ? "amber" : "emerald"}
          icon={AlertTriangle}
          subtext="CPU/Latency elevated"
        />
        <MetricCard
          title="Insufficient Telemetry"
          value={countInsufficient}
          unit="services"
          variant={countInsufficient > 0 ? "rose" : "emerald"}
          icon={HelpCircle}
          subtext={countInsufficient === 0 ? "100% complete" : "Excluded from scale"}
        />
        <MetricCard
          title="Highest Severity"
          value={bottleneckService || "None"}
          variant={bottleneckService ? "rose" : "emerald"}
          icon={Flame}
          subtext={bottleneckService ? "Prioritized for scale-up" : "All services nominal"}
        />
        <MetricCard
          title="Deployment Phase"
          value={pipeline?.deployment_phase || health?.deployment_phase || "NORMAL_OPERATION"}
          variant="purple"
          icon={Layers}
          subtext="Weighting active"
          to="/deployments"
        />
      </div>

      {/* Section B: Bottleneck Severity Breakdown Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div
          onClick={() => setSeverityFilter(severityFilter === "BOTTLENECK" ? "ALL" : "BOTTLENECK")}
          className={`p-4 rounded-xl border cursor-pointer transition-all ${
            severityFilter === "BOTTLENECK"
              ? "bg-rose-500/10 border-rose-500/60 shadow-[0_0_15px_rgba(239,68,68,0.2)]"
              : "bg-canvas-card border-canvas-border hover:border-rose-500/40"
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-rose-400 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
              <span>BOTTLENECK (Critical)</span>
            </span>
            <span className="font-mono text-sm font-bold text-rose-400">{countBottlenecks}</span>
          </div>
          <p className="text-[11px] text-text-secondary leading-snug">
            Flagged by DPBPS as the root system constraint causing upstream latency amplification.
          </p>
        </div>

        <div
          onClick={() => setSeverityFilter(severityFilter === "UNDER_PRESSURE" ? "ALL" : "UNDER_PRESSURE")}
          className={`p-4 rounded-xl border cursor-pointer transition-all ${
            severityFilter === "UNDER_PRESSURE"
              ? "bg-amber-500/10 border-amber-500/60 shadow-[0_0_15px_rgba(245,158,11,0.2)]"
              : "bg-canvas-card border-canvas-border hover:border-amber-500/40"
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-amber-400 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              <span>UNDER PRESSURE (Warning)</span>
            </span>
            <span className="font-mono text-sm font-bold text-amber-400">{countPressure}</span>
          </div>
          <p className="text-[11px] text-text-secondary leading-snug">
            Elevated CPU (&ge;70%) or latency (&gt;200ms) with proactive scale-up recommended.
          </p>
        </div>

        <div
          onClick={() => setSeverityFilter(severityFilter === "HEALTHY" ? "ALL" : "HEALTHY")}
          className={`p-4 rounded-xl border cursor-pointer transition-all ${
            severityFilter === "HEALTHY"
              ? "bg-emerald-500/10 border-emerald-500/60 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
              : "bg-canvas-card border-canvas-border hover:border-emerald-500/40"
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-emerald-400 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span>HEALTHY (Nominal)</span>
            </span>
            <span className="font-mono text-sm font-bold text-emerald-400">{countHealthy}</span>
          </div>
          <p className="text-[11px] text-text-secondary leading-snug">
            Operating within capacity boundaries; DPBPS maintains steady-state HOLD decisions.
          </p>
        </div>

        <div
          onClick={() => setSeverityFilter(severityFilter === "INSUFFICIENT_TELEMETRY" ? "ALL" : "INSUFFICIENT_TELEMETRY")}
          className={`p-4 rounded-xl border cursor-pointer transition-all ${
            severityFilter === "INSUFFICIENT_TELEMETRY"
              ? "bg-slate-500/10 border-slate-500/60 shadow-[0_0_15px_rgba(148,163,184,0.2)]"
              : "bg-canvas-card border-canvas-border hover:border-slate-500/40"
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-slate-400 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-400" />
              <span>INSUFFICIENT TELEMETRY</span>
            </span>
            <span className="font-mono text-sm font-bold text-slate-400">{countInsufficient}</span>
          </div>
          <p className="text-[11px] text-text-secondary leading-snug">
            Missing Prometheus metrics; excluded from scaling decisions to preserve stability.
          </p>
        </div>
      </div>

      {/* Section C: Service-Level Bottleneck Table */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <SectionHeader
            title="Service-Level Bottleneck Diagnostic Table"
            subtitle="Click any row to inspect deep dependency impact propagation and supporting evidence"
            icon={Flame}
          />

          <div className="flex items-center space-x-2">
            <div className="w-64 relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search service..."
                className="w-full bg-canvas-dark border border-canvas-border rounded-lg pl-9 pr-3 py-1.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-cyan-500/50"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                >
                  <X size={13} />
                </button>
              )}
            </div>

            {severityFilter !== "ALL" && (
              <button
                onClick={() => setSeverityFilter("ALL")}
                className="text-xs text-cyan-400 hover:text-cyan-300 font-medium px-2 py-1 rounded bg-canvas-dark border border-canvas-border"
              >
                Clear Filter
              </button>
            )}
          </div>
        </div>

        <DataTable
          data={filteredRows}
          columns={columns}
          keyExtractor={(r) => r.name}
          onRowClick={(r) => setSelectedService(r)}
          emptyMessage="No microservices match the selected severity filter."
        />
      </div>

      {/* Sections D, E, F: Detailed Service Inspection, Dependency Impact & Recommended Action */}
      {selectedService && (
        <div className="bg-canvas-card border border-canvas-border rounded-xl p-5 shadow-card space-y-6">
          <div className="flex items-center justify-between pb-3 border-b border-canvas-border">
            <div className="flex items-center space-x-3">
              <span className="font-bold text-base text-text-primary">
                {selectedService.name}
              </span>
              <StatusBadge
                status={selectedService.severity}
                variant={
                  selectedService.severity === "BOTTLENECK"
                    ? "rose"
                    : selectedService.severity === "UNDER_PRESSURE"
                    ? "amber"
                    : selectedService.severity === "INSUFFICIENT_TELEMETRY"
                    ? "slate"
                    : "emerald"
                }
              />
              {selectedService.name === bottleneckService && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse">
                  PRIMARY SYSTEM BOTTLENECK
                </span>
              )}
            </div>
            <Link
              to="/topology"
              className="text-xs text-cyan-400 hover:text-cyan-300 font-medium flex items-center space-x-1"
            >
              <Network size={13} />
              <span>View in Call-Graph Topology &rarr;</span>
            </Link>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Section D: Dependency Impact Analysis */}
            <div className="bg-canvas-dark border border-canvas-border rounded-xl p-4 space-y-3 text-xs">
              <div className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider flex items-center space-x-1.5">
                <Network size={14} className="text-cyan-400" />
                <span>Dependency Impact Analysis</span>
              </div>

              {/* Upstream Callers */}
              <div className="space-y-1">
                <span className="text-text-muted text-[11px] flex items-center space-x-1">
                  <ArrowDownRight size={13} className="text-amber-400" />
                  <span>Upstream Callers ({incomingMap[selectedService.name]?.length ?? 0}):</span>
                </span>
                {incomingMap[selectedService.name] && incomingMap[selectedService.name].length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {incomingMap[selectedService.name].map((caller) => (
                      <span
                        key={caller}
                        className="px-2 py-0.5 rounded bg-canvas-card border border-canvas-border text-amber-300 font-mono text-[10px]"
                      >
                        {caller}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-text-muted text-[11px] italic block">Ingress root microservice</span>
                )}
              </div>

              {/* Downstream Dependencies */}
              <div className="space-y-1 pt-2 border-t border-canvas-border">
                <span className="text-text-muted text-[11px] flex items-center space-x-1">
                  <ArrowRight size={13} className="text-cyan-400" />
                  <span>Downstream Dependencies ({selectedService.dependencies.length}):</span>
                </span>
                {selectedService.dependencies.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {selectedService.dependencies.map((dep) => (
                      <span
                        key={dep}
                        className="px-2 py-0.5 rounded bg-canvas-card border border-canvas-border text-cyan-400 font-mono text-[10px]"
                      >
                        {dep}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-text-muted text-[11px] italic block">Leaf microservice (zero downstream dependencies)</span>
                )}
              </div>

              {/* Cascade Explanation */}
              <div className="pt-2 border-t border-canvas-border text-[11px] text-text-secondary leading-relaxed font-sans">
                {selectedService.severity === "BOTTLENECK" ? (
                  <p className="text-rose-300/90">
                    <strong className="text-rose-400 font-semibold">Latency Amplification:</strong> As {selectedService.name} saturates, upstream callers ({incomingMap[selectedService.name]?.join(", ") || "clients"}) block waiting for responses, compounding cluster-wide P95 latency.
                  </p>
                ) : (
                  <p>
                    {selectedService.name} is currently responding within normal thresholds. Downstream services do not exhibit backpressure propagation.
                  </p>
                )}
              </div>
            </div>

            {/* Section E: Bottleneck Evidence */}
            <div className="bg-canvas-dark border border-canvas-border rounded-xl p-4 space-y-3 text-xs">
              <div className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider flex items-center space-x-1.5">
                <Activity size={14} className="text-blue-400" />
                <span>Supporting Bottleneck Evidence</span>
              </div>

              <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                <div className="p-2 rounded bg-canvas-card border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">CPU PRESSURE</span>
                  <span className={`font-bold ${selectedService.cpuUtilisation >= 0.7 ? "text-rose-400" : "text-text-primary"}`}>
                    {selectedService.telemetryAvailable ? `${(selectedService.cpuUtilisation * 100).toFixed(1)}%` : "N/A"}
                  </span>
                  <span className="text-[9px] text-text-muted block font-sans">Trigger: &ge;70%</span>
                </div>
                <div className="p-2 rounded bg-canvas-card border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">P95 LATENCY</span>
                  <span className={`font-bold ${selectedService.p95Latency > 200 ? "text-rose-400" : "text-text-primary"}`}>
                    {selectedService.telemetryAvailable ? `${selectedService.p95Latency.toFixed(1)} ms` : "N/A"}
                  </span>
                  <span className="text-[9px] text-text-muted block font-sans">SLA: &le;200ms</span>
                </div>
                <div className="p-2 rounded bg-canvas-card border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">REQUEST THROUGHPUT</span>
                  <span className="font-bold text-text-primary">
                    {selectedService.telemetryAvailable ? `${selectedService.requestRate.toFixed(1)} req/s` : "N/A"}
                  </span>
                </div>
                <div className="p-2 rounded bg-canvas-card border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">ERROR FRACTION</span>
                  <span className="font-bold text-text-muted">
                    {selectedService.telemetryAvailable ? `${(selectedService.errorRate * 100).toFixed(2)}%` : "N/A"}
                  </span>
                </div>
              </div>

              <div className="pt-2 border-t border-canvas-border text-[11px] text-text-muted">
                <span>Telemetry Status: </span>
                <span className={selectedService.telemetryAvailable ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                  {selectedService.telemetryAvailable ? "COMPLETE & FRESH" : "INSUFFICIENT"}
                </span>
                <span className="block text-[10px] text-text-muted mt-0.5">
                  Source: Live Prometheus metrics endpoint &bull; Scraped: {lastRefreshed}
                </span>
              </div>
            </div>

            {/* Section F: Recommended Action */}
            <div className="bg-canvas-dark border border-canvas-border rounded-xl p-4 space-y-3 text-xs flex flex-col justify-between">
              <div className="space-y-2.5">
                <div className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider flex items-center space-x-1.5">
                  <ShieldCheck size={14} className="text-amber-400" />
                  <span>DPBPS Algorithmic Recommendation</span>
                </div>

                <div className="flex items-center justify-between p-2.5 rounded-lg bg-canvas-card border border-canvas-border">
                  <div>
                    <span className="text-[10px] text-text-muted block">RECOMMENDED ACTION</span>
                    <span className="font-bold text-sm text-text-primary">{selectedService.decisionAction}</span>
                  </div>
                  <StatusBadge
                    status={selectedService.decisionAction}
                    variant={
                      selectedService.decisionAction === "SCALE_UP"
                        ? "rose"
                        : selectedService.decisionAction === "SCALE_DOWN"
                        ? "amber"
                        : selectedService.decisionAction === "EXCLUDED"
                        ? "slate"
                        : "emerald"
                    }
                  />
                </div>

                <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                  <div className="p-2 rounded bg-canvas-card border border-canvas-border">
                    <span className="text-text-muted text-[10px] block font-sans">CURRENT REPLICAS</span>
                    <span className="font-bold text-cyan-400">{selectedService.readyReplicas} Pods</span>
                  </div>
                  <div className="p-2 rounded bg-canvas-card border border-canvas-border">
                    <span className="text-text-muted text-[10px] block font-sans">PROPOSED TARGET</span>
                    <span className="font-bold text-text-primary">
                      {selectedService.pipelineResult?.proposed_replica_count ?? selectedService.desiredReplicas} Pods
                    </span>
                  </div>
                </div>

                <div className="p-2.5 rounded bg-canvas-card/50 border border-canvas-border text-[11px] text-text-secondary leading-relaxed">
                  <span className="font-semibold text-text-primary block mb-0.5">Decision Reason:</span>
                  {selectedService.reason}
                </div>
              </div>

              {/* Safety Disclaimers */}
              <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-300/90 leading-tight">
                <strong>DRY_RUN Enforcement:</strong> This recommendation is a simulation validated against safety bounds. Live cluster mutations are inhibited (`SCALING_ENABLED=false`).
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
