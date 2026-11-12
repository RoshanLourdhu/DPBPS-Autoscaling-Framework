// src/pages/ServicesPage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  fetchServices,
  fetchPipelineEvaluation,
} from "../services/api";
import type {
  ServiceInfo,
  PipelineEvaluationResponse,
  PipelineServiceResult,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { StatusBadge } from "../components/ui/StatusBadge";
import { DataTable } from "../components/ui/DataTable";
import type { ColumnDef } from "../components/ui/DataTable";
import { SearchBar } from "../components/ui/SearchBar";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  Boxes,
  CheckCircle2,
  Flame,
  Activity,
  Cpu,
  HardDrive,
  RefreshCw,
  LayoutGrid,
  Table as TableIcon,
  X,
  Network,
  ArrowRight,
  ArrowDownRight,
  Info,
  Zap,
} from "lucide-react";

export default function ServicesPage() {
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [pipeline, setPipeline] = useState<PipelineEvaluationResponse | null>(null);
  const [selectedService, setSelectedService] = useState<ServiceInfo | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "HEALTHY" | "DEGRADED" | "BOTTLENECK">("ALL");
  const [viewMode, setViewMode] = useState<"table" | "grid">("table");
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  const loadData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [svcData, pipeData] = await Promise.all([
        fetchServices(),
        fetchPipelineEvaluation(),
      ]);
      setServices(svcData);
      setPipeline(pipeData);
      setLastRefreshed(new Date().toLocaleTimeString());
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load microservices inventory.");
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

  // Map pipeline decisions by service name
  const decisionMap = useMemo(() => {
    const map: Record<string, PipelineServiceResult> = {};
    if (pipeline?.services) {
      pipeline.services.forEach((ps) => {
        map[ps.service_name] = ps;
      });
    }
    return map;
  }, [pipeline]);

  // Filtering
  const filteredServices = useMemo(() => {
    return services.filter((svc) => {
      // Status filter
      if (statusFilter === "HEALTHY" && svc.health !== "HEALTHY") return false;
      if (statusFilter === "DEGRADED" && svc.health !== "DEGRADED") return false;
      if (statusFilter === "BOTTLENECK" && svc.name !== bottleneckService) return false;

      // Text query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = svc.name.toLowerCase().includes(q);
        const matchesDep = (svc.dependencies || []).some((d) => d.toLowerCase().includes(q));
        if (!matchesName && !matchesDep) return false;
      }

      return true;
    });
  }, [services, statusFilter, bottleneckService, searchQuery]);

  // Summary Metrics
  const totalCount = services.length;
  const healthyCount = services.filter((s) => s.health === "HEALTHY").length;
  const incompleteCount = services.filter((s) => !s.telemetry_available).length;

  // Table Columns
  const columns: ColumnDef<ServiceInfo>[] = [
    {
      key: "name",
      header: "Microservice",
      render: (s) => (
        <div className="flex items-center space-x-2">
          <span className="font-bold text-text-primary group-hover:text-cyan-400 transition-colors">
            {s.name}
          </span>
          {s.name === bottleneckService && (
            <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">
              BOTTLENECK
            </span>
          )}
        </div>
      ),
      sortable: true,
      width: "180px",
    },
    {
      key: "health",
      header: "Status",
      render: (s) => (
        <StatusBadge
          status={s.health}
          variant={s.health === "HEALTHY" ? "emerald" : "amber"}
          size="xs"
        />
      ),
      align: "center",
      sortable: true,
      width: "100px",
    },
    {
      key: "ready_replicas",
      header: "Replicas",
      render: (s) => (
        <span className="font-mono text-cyan-400 font-bold">
          {s.ready_replicas} / {s.desired_replicas ?? s.ready_replicas}
        </span>
      ),
      align: "center",
      sortable: true,
      width: "110px",
    },
    {
      key: "request_rate",
      header: "Throughput",
      render: (s) => (
        <span className="font-mono font-bold text-text-primary">
          {s.telemetry_available ? (
            <>
              {s.request_rate.toFixed(1)}{" "}
              <span className="text-text-muted text-[10px] font-normal">req/s</span>
            </>
          ) : (
            <span className="text-text-muted text-xs font-normal">N/A*</span>
          )}
        </span>
      ),
      align: "right",
      sortable: true,
      width: "120px",
    },
    {
      key: "p95_latency",
      header: "P95 Latency",
      render: (s) => {
        if (!s.telemetry_available) {
          return <span className="font-mono text-text-muted text-xs">N/A*</span>;
        }
        const isViolated = s.p95_latency > 200;
        return (
          <span className={`font-mono font-bold ${isViolated ? "text-rose-400" : "text-text-primary"}`}>
            {s.p95_latency.toFixed(1)}{" "}
            <span className="text-text-muted text-[10px] font-normal">ms</span>
          </span>
        );
      },
      align: "right",
      sortable: true,
      width: "120px",
    },
    {
      key: "p50_p99",
      header: "P50 / P99",
      render: () => (
        <span
          className="text-text-muted font-mono text-[11px]"
          title="P95 is the canonical SLA metric scraped by Prometheus; P50/P99 not exported by application endpoint."
        >
          N/A*
        </span>
      ),
      align: "center",
      width: "90px",
    },
    {
      key: "cpu_utilisation",
      header: "CPU Utilization",
      render: (s) => {
        const cpu = s.cpu_utilisation ?? 0;
        const pct = (cpu * 100).toFixed(1);
        const isHigh = cpu >= 0.7;
        return (
          <div className="flex items-center space-x-2 font-mono">
            <div className="w-16 bg-canvas-dark rounded-full h-1.5 overflow-hidden border border-canvas-border">
              <div
                className={`h-full rounded-full ${isHigh ? "bg-rose-500" : "bg-cyan-400"}`}
                style={{ width: `${Math.min(100, cpu * 100)}%` }}
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
      width: "140px",
    },
    {
      key: "memory_utilisation",
      header: "Memory Utilization",
      render: (s) => {
        const mem = s.memory_utilisation ?? 0;
        const pct = (mem * 100).toFixed(1);
        return (
          <div className="flex items-center space-x-2 font-mono">
            <div className="w-16 bg-canvas-dark rounded-full h-1.5 overflow-hidden border border-canvas-border">
              <div
                className="h-full rounded-full bg-blue-400"
                style={{ width: `${Math.min(100, mem * 100)}%` }}
              />
            </div>
            <span className="text-text-primary">{pct}%</span>
          </div>
        );
      },
      align: "left",
      sortable: true,
      width: "140px",
    },
    {
      key: "error_rate",
      header: "Error Rate",
      render: (s) => (
        <span className="font-mono text-text-muted">
          {s.telemetry_available ? `${(s.error_rate * 100).toFixed(2)}%` : "N/A*"}
        </span>
      ),
      align: "right",
      sortable: true,
      width: "100px",
    },
    {
      key: "dependencies",
      header: "Dependencies",
      render: (s) => (
        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-canvas-dark text-cyan-400 border border-canvas-border">
          {s.dependencies?.length ?? 0} outgoing
        </span>
      ),
      align: "center",
      width: "110px",
    },
  ];

  if (loading) return <LoadingState message="Loading microservices telemetry..." />;
  if (error && services.length === 0) return <ErrorState message={error} onRetry={() => loadData(true)} />;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Microservices Inventory & Telemetry"
        subtitle="Live application metrics, container resource consumption, and call-graph dependencies for the 10 Online Boutique microservices."
        badge={
          <StatusBadge
            status={`${healthyCount}/${totalCount} HEALTHY`}
            variant={healthyCount === totalCount ? "emerald" : "amber"}
          />
        }
        actions={
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-canvas-border bg-canvas-card hover:bg-canvas-hover text-xs font-medium text-text-secondary hover:text-text-primary disabled:opacity-50 transition-colors"
            title={`Last refreshed: ${lastRefreshed}`}
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin text-cyan-400" : ""} />
            <span>Refresh Telemetry</span>
          </button>
        }
      />

      {/* Summary KPI Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Tracked Microservices"
          value={totalCount}
          unit="services"
          variant="cyan"
          icon={Boxes}
          subtext="Namespace: online-boutique"
        />
        <MetricCard
          title="Healthy Telemetry"
          value={`${healthyCount}/${totalCount}`}
          variant={healthyCount === totalCount ? "emerald" : "amber"}
          icon={CheckCircle2}
          subtext="Responsive to metrics scraper"
        />
        <MetricCard
          title="Telemetry Completeness"
          value={incompleteCount === 0 ? "100.0" : ((1 - incompleteCount / totalCount) * 100).toFixed(1)}
          unit="%"
          variant={incompleteCount === 0 ? "emerald" : "rose"}
          icon={Activity}
          subtext={incompleteCount === 0 ? "Zero missing metrics" : `${incompleteCount} services incomplete`}
        />
        <MetricCard
          title="Active Bottleneck"
          value={bottleneckService || "None"}
          variant={bottleneckService ? "rose" : "emerald"}
          icon={Flame}
          subtext={bottleneckService ? "DPBPS scaling prioritized" : "All services nominal"}
          to="/bottlenecks"
        />
      </div>

      {/* Controls & Filter Bar */}
      <div className="bg-canvas-card border border-canvas-border rounded-xl p-4 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Left: Search Bar */}
        <div className="w-full sm:w-72">
          <SearchBar
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search service or dependency..."
          />
        </div>

        {/* Right: Status Filters & View Toggle */}
        <div className="flex items-center space-x-2 self-end sm:self-auto flex-wrap gap-y-2">
          {/* Status Filter Buttons */}
          <div className="flex items-center space-x-1 p-1 rounded-lg bg-canvas-dark border border-canvas-border text-xs">
            <button
              onClick={() => setStatusFilter("ALL")}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                statusFilter === "ALL" ? "bg-canvas-elevated text-text-primary font-semibold" : "text-text-muted hover:text-text-primary"
              }`}
            >
              All ({totalCount})
            </button>
            <button
              onClick={() => setStatusFilter("HEALTHY")}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                statusFilter === "HEALTHY" ? "bg-emerald-500/20 text-emerald-400 font-semibold" : "text-text-muted hover:text-text-primary"
              }`}
            >
              Healthy ({healthyCount})
            </button>
            <button
              onClick={() => setStatusFilter("BOTTLENECK")}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                statusFilter === "BOTTLENECK" ? "bg-rose-500/20 text-rose-400 font-semibold" : "text-text-muted hover:text-text-primary"
              }`}
            >
              Bottleneck
            </button>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center space-x-1 p-1 rounded-lg bg-canvas-dark border border-canvas-border text-xs">
            <button
              onClick={() => setViewMode("table")}
              className={`p-1.5 rounded-md transition-colors ${
                viewMode === "table" ? "bg-cyan-500/20 text-cyan-400" : "text-text-muted hover:text-text-primary"
              }`}
              title="Table View"
            >
              <TableIcon size={14} />
            </button>
            <button
              onClick={() => setViewMode("grid")}
              className={`p-1.5 rounded-md transition-colors ${
                viewMode === "grid" ? "bg-cyan-500/20 text-cyan-400" : "text-text-muted hover:text-text-primary"
              }`}
              title="Card Grid View"
            >
              <LayoutGrid size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area: Table or Card Grid */}
      {viewMode === "table" ? (
        <div className="space-y-2">
          <DataTable
            data={filteredServices}
            columns={columns}
            keyExtractor={(s) => s.id}
            searchable={false}
            onRowClick={(s) => setSelectedService(s)}
            emptyMessage="No microservices match the selected filters."
          />
          <div className="flex items-center space-x-1.5 text-[11px] text-text-muted px-2">
            <Info size={12} className="text-cyan-400 flex-shrink-0" />
            <span>
              *P95 latency is the canonical SLA metric scraped by Prometheus via <code className="font-mono text-cyan-400">histogram_quantile</code>. P50/P99 are not exported by microservice metric ports and are withheld rather than fabricated.
            </span>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredServices.map((svc) => {
            const isBottleneck = svc.name === bottleneckService;
            const isHighCpu = svc.cpu_utilisation >= 0.7;

            return (
              <div
                key={svc.id}
                onClick={() => setSelectedService(svc)}
                className={`bg-canvas-card border rounded-xl p-5 shadow-card cursor-pointer transition-all hover:-translate-y-0.5 space-y-4 ${
                  isBottleneck
                    ? "border-rose-500/60 shadow-[0_0_15px_rgba(239,68,68,0.15)]"
                    : "border-canvas-border hover:border-cyan-500/50"
                }`}
              >
                {/* Header */}
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-sm text-text-primary flex items-center space-x-2">
                      <span>{svc.name}</span>
                      {isBottleneck && (
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse">
                          BOTTLENECK
                        </span>
                      )}
                    </h3>
                    <span className="text-[11px] text-text-muted font-mono">
                      Namespace: {svc.environment_id}
                    </span>
                  </div>
                  <StatusBadge
                    status={svc.health}
                    variant={svc.health === "HEALTHY" ? "emerald" : "amber"}
                    size="xs"
                  />
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 gap-2.5 p-3 rounded-lg bg-canvas-dark border border-canvas-border font-mono text-xs">
                  <div>
                    <span className="text-text-muted text-[10px] block font-sans">THROUGHPUT</span>
                    <span className="font-bold text-text-primary">
                      {svc.telemetry_available ? `${svc.request_rate.toFixed(1)} req/s` : "N/A*"}
                    </span>
                  </div>
                  <div>
                    <span className="text-text-muted text-[10px] block font-sans">P95 LATENCY</span>
                    <span className={`font-bold ${svc.p95_latency > 200 ? "text-rose-400" : "text-text-primary"}`}>
                      {svc.telemetry_available ? `${svc.p95_latency.toFixed(1)} ms` : "N/A*"}
                    </span>
                  </div>
                  <div>
                    <span className="text-text-muted text-[10px] block font-sans">CPU UTILIZATION</span>
                    <span className={`font-bold ${isHighCpu ? "text-rose-400" : "text-cyan-400"}`}>
                      {(svc.cpu_utilisation * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-text-muted text-[10px] block font-sans">MEMORY UTIL.</span>
                    <span className="font-bold text-blue-400">
                      {(svc.memory_utilisation * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-text-muted text-[10px] block font-sans">REPLICAS (READY/DES)</span>
                    <span className="font-bold text-text-primary">
                      {svc.ready_replicas} / {svc.desired_replicas ?? svc.ready_replicas}
                    </span>
                  </div>
                  <div>
                    <span className="text-text-muted text-[10px] block font-sans">ERROR RATE</span>
                    <span className="font-bold text-text-muted">
                      {svc.telemetry_available ? `${(svc.error_rate * 100).toFixed(2)}%` : "N/A*"}
                    </span>
                  </div>
                </div>

                {/* Footer Dependencies */}
                <div className="pt-2 border-t border-canvas-border flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-1.5 text-text-muted text-[11px]">
                    <Network size={13} className="text-cyan-400" />
                    <span>{svc.dependencies?.length ?? 0} Downstream</span>
                  </div>
                  <span className="text-cyan-400 hover:text-cyan-300 font-medium text-[11px] flex items-center space-x-0.5">
                    <span>Inspect Details</span>
                    <ArrowRight size={11} />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Individual Service Inspector Slide-Over Panel */}
      {selectedService && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-xl h-full bg-canvas-card border-l border-canvas-border shadow-2xl p-6 overflow-y-auto space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between pb-4 border-b border-canvas-border">
              <div className="space-y-1">
                <div className="flex items-center space-x-2.5">
                  <h2 className="text-lg font-bold text-text-primary">{selectedService.name}</h2>
                  <StatusBadge
                    status={selectedService.health}
                    variant={selectedService.health === "HEALTHY" ? "emerald" : "amber"}
                    size="xs"
                  />
                  {selectedService.name === bottleneckService && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">
                      BOTTLENECK
                    </span>
                  )}
                </div>
                <p className="text-xs text-text-muted font-mono">
                  Namespace: {selectedService.environment_id} &bull; Deployment Phase: {selectedService.deployment_phase || "NORMAL_OPERATION"}
                </p>
              </div>
              <button
                onClick={() => setSelectedService(null)}
                className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-canvas-hover transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Quad Key Metrics */}
            <div className="grid grid-cols-2 gap-3">
              <MetricCard
                title="CPU Utilization"
                value={`${(selectedService.cpu_utilisation * 100).toFixed(1)}`}
                unit="%"
                variant={selectedService.cpu_utilisation >= 0.7 ? "rose" : "cyan"}
                icon={Cpu}
                subtext="Pod aggregate vs requests"
              />
              <MetricCard
                title="Memory Utilization"
                value={`${(selectedService.memory_utilisation * 100).toFixed(1)}`}
                unit="%"
                variant="blue"
                icon={HardDrive}
                subtext="Working set vs requests"
              />
              <MetricCard
                title="Throughput Rate"
                value={selectedService.telemetry_available ? selectedService.request_rate.toFixed(1) : "N/A*"}
                unit={selectedService.telemetry_available ? "req/s" : ""}
                variant="cyan"
                icon={Activity}
                subtext={selectedService.telemetry_available ? "HTTP / gRPC traffic" : "Telemetry unavailable (idle / uninstrumented)"}
              />
              <MetricCard
                title="P95 Latency"
                value={selectedService.telemetry_available ? selectedService.p95_latency.toFixed(1) : "N/A*"}
                unit={selectedService.telemetry_available ? "ms" : ""}
                variant={selectedService.p95_latency > 200 ? "rose" : "blue"}
                icon={Zap}
                subtext={selectedService.telemetry_available ? "SLA threshold: 200ms" : "Telemetry unavailable (idle / uninstrumented)"}
              />
            </div>

            {/* Kubernetes Deployment & Readiness Status */}
            <div className="bg-canvas-dark border border-canvas-border rounded-xl p-4 space-y-3 font-mono text-xs">
              <div className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider font-sans">
                Kubernetes Pod & Replica Status
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border">
                  <span className="text-[10px] text-text-muted block font-sans">READY REPLICAS</span>
                  <span className="text-sm font-bold text-cyan-400">{selectedService.ready_replicas} Pods</span>
                </div>
                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border">
                  <span className="text-[10px] text-text-muted block font-sans">DESIRED REPLICAS</span>
                  <span className="text-sm font-bold text-text-primary">{selectedService.desired_replicas ?? selectedService.ready_replicas} Pods</span>
                </div>
              </div>
            </div>

            {/* Call Graph Dependencies (Incoming & Outgoing) */}
            <div className="bg-canvas-dark border border-canvas-border rounded-xl p-4 space-y-4 text-xs">
              <div className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider">
                Call-Graph Dependency Topology
              </div>

              {/* Incoming Callers */}
              <div>
                <span className="text-text-muted text-[11px] block mb-1.5 flex items-center space-x-1">
                  <ArrowDownRight size={13} className="text-amber-400" />
                  <span>Incoming Callers ({incomingMap[selectedService.name]?.length ?? 0}):</span>
                </span>
                {incomingMap[selectedService.name] && incomingMap[selectedService.name].length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {incomingMap[selectedService.name].map((caller) => (
                      <span
                        key={caller}
                        className="px-2.5 py-1 rounded-md bg-canvas-card border border-canvas-border text-amber-300 font-mono text-[11px]"
                      >
                        {caller}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-text-muted text-[11px] italic">Ingress root service (called by external traffic)</span>
                )}
              </div>

              {/* Outgoing Dependencies */}
              <div>
                <span className="text-text-muted text-[11px] block mb-1.5 flex items-center space-x-1">
                  <ArrowRight size={13} className="text-cyan-400" />
                  <span>Outgoing Downstream Services ({selectedService.dependencies?.length ?? 0}):</span>
                </span>
                {selectedService.dependencies && selectedService.dependencies.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedService.dependencies.map((dep) => (
                      <span
                        key={dep}
                        className="px-2.5 py-1 rounded-md bg-canvas-card border border-canvas-border text-cyan-400 font-mono text-[11px]"
                      >
                        {dep}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-text-muted text-[11px] italic">Leaf service (no downstream calls)</span>
                )}
              </div>
            </div>

            {/* Latest DPBPS Decision Context */}
            {decisionMap[selectedService.name] && (
              <div className="bg-canvas-dark border border-canvas-border rounded-xl p-4 space-y-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-text-secondary text-[11px] uppercase tracking-wider">
                    Latest DPBPS Scaling Recommendation
                  </span>
                  <StatusBadge
                    status={decisionMap[selectedService.name].dpbps_decision}
                    variant={
                      decisionMap[selectedService.name].dpbps_decision === "SCALE_UP"
                        ? "rose"
                        : decisionMap[selectedService.name].dpbps_decision === "SCALE_DOWN"
                        ? "amber"
                        : "emerald"
                    }
                    size="xs"
                  />
                </div>
                <div className="p-2.5 rounded bg-canvas-card border border-canvas-border font-mono text-[11px] text-text-secondary">
                  Target: <span className="text-cyan-400 font-bold">{decisionMap[selectedService.name].current_replicas} &rarr; {decisionMap[selectedService.name].proposed_replica_count} Replicas</span> &bull; Actuator: <span className="text-amber-400 font-bold">DRY_RUN (SIMULATED)</span>
                </div>
                <p className="text-text-secondary text-[11px] leading-relaxed">
                  {decisionMap[selectedService.name].reason}
                </p>
              </div>
            )}

            {/* Navigation Actions */}
            <div className="pt-2 flex items-center justify-between">
              <Link
                to="/topology"
                className="flex items-center space-x-1.5 text-xs text-cyan-400 hover:text-cyan-300 font-medium"
              >
                <Network size={14} />
                <span>View in Service Call-Graph Topology &rarr;</span>
              </Link>
              <button
                onClick={() => setSelectedService(null)}
                className="px-3.5 py-1.5 rounded-lg border border-canvas-border bg-canvas-elevated hover:bg-canvas-hover text-xs font-medium text-text-secondary"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
