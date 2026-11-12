// src/pages/OverviewDashboard.tsx
import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchHealth,
  fetchServices,
  fetchPipelineEvaluation,
  triggerPipelineEvaluation,
  updateDeploymentPhase,
  DEPLOYMENT_PHASES,
} from "../services/api";
import type {
  HealthResponse,
  ServiceInfo,
  PipelineEvaluationResponse,
  DeploymentPhase,
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
  Boxes,
  CheckCircle2,
  Flame,
  Activity,
  Zap,
  Brain,
  ShieldCheck,
  RefreshCw,
  Server,
  Layers,
  Radio,
  ExternalLink,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";

interface TelemetrySnapshot {
  time: string;
  throughput: number;
  avgLatency: number;
  avgCpu: number;
  avgMemory: number;
  errorRate: number;
}

export default function OverviewDashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [pipeline, setPipeline] = useState<PipelineEvaluationResponse | null>(null);
  const [history, setHistory] = useState<TelemetrySnapshot[]>([]);
  const [selectedPhase, setSelectedPhase] = useState<DeploymentPhase | string>("NORMAL_OPERATION");
  const [chartMetric, setChartMetric] = useState<"throughput" | "latency" | "cpu">("throughput");
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  const navigate = useNavigate();

  const loadData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [h, svc, pipe] = await Promise.all([
        fetchHealth(),
        fetchServices(),
        fetchPipelineEvaluation(),
      ]);

      setHealth(h);
      setServices(svc);
      setPipeline(pipe);
      const activePhase = pipe.deployment_phase || h.deployment_phase;
      if (activePhase) {
        setSelectedPhase(activePhase);
      }
      setLastRefreshed(new Date().toLocaleTimeString());

      // Append new snapshot to rolling history
      const totalThroughput = svc.reduce((sum, s) => sum + (s.request_rate || 0), 0);
      const activeServices = svc.filter((s) => (s.request_rate || 0) > 0);
      const avgLatency =
        activeServices.length > 0
          ? activeServices.reduce((sum, s) => sum + (s.p95_latency || 0), 0) / activeServices.length
          : svc.reduce((sum, s) => sum + (s.p95_latency || 0), 0) / Math.max(1, svc.length);
      const avgCpu =
        svc.reduce((sum, s) => sum + (s.cpu_utilisation || 0), 0) / Math.max(1, svc.length) * 100;
      const avgMemory =
        svc.reduce((sum, s) => sum + (s.memory_utilisation || 0), 0) / Math.max(1, svc.length) * 100;
      const errorRate =
        svc.reduce((sum, s) => sum + (s.error_rate || 0), 0) / Math.max(1, svc.length) * 100;

      const newSnapshot: TelemetrySnapshot = {
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        throughput: parseFloat(totalThroughput.toFixed(1)),
        avgLatency: parseFloat(avgLatency.toFixed(1)),
        avgCpu: parseFloat(avgCpu.toFixed(1)),
        avgMemory: parseFloat(avgMemory.toFixed(1)),
        errorRate: parseFloat(errorRate.toFixed(2)),
      };

      setHistory((prev) => [...prev.slice(-14), newSnapshot]);
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

  const handlePhaseChange = async (newPhase: DeploymentPhase | string) => {
    try {
      const res = await updateDeploymentPhase(newPhase);
      setSelectedPhase(res?.phase || newPhase);
      await loadData(false);
    } catch (e: any) {
      setError(`Phase update failed: ${e.message}`);
    }
  };

  // KPI Computations
  const totalServicesCount = services.length;
  const healthyServicesCount = services.filter((s) => s.health === "HEALTHY").length;
  const bottleneckService = pipeline?.bottleneck_service;
  const totalThroughput = services.reduce((sum, s) => sum + (s.request_rate || 0), 0);
  const activeServices = services.filter((s) => (s.request_rate || 0) > 0);
  const averageLatency =
    activeServices.length > 0
      ? activeServices.reduce((sum, s) => sum + (s.p95_latency || 0), 0) / activeServices.length
      : services.reduce((sum, s) => sum + (s.p95_latency || 0), 0) / Math.max(1, services.length);

  // Table Columns
  const serviceColumns: ColumnDef<ServiceInfo>[] = [
    {
      key: "name",
      header: "Microservice",
      render: (s) => (
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-text-primary">{s.name}</span>
          {s.name === bottleneckService && (
            <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">
              BOTTLENECK
            </span>
          )}
        </div>
      ),
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
      width: "100px",
    },
    {
      key: "ready_replicas",
      header: "Replicas (Ready/Des)",
      render: (s) => (
        <span className="font-mono text-cyan-400 font-bold">
          {s.ready_replicas} / {s.desired_replicas ?? s.ready_replicas}
        </span>
      ),
      align: "center",
      width: "130px",
    },
    {
      key: "cpu_utilisation",
      header: "CPU Utilization",
      render: (s) => {
        const pct = (s.cpu_utilisation * 100).toFixed(1);
        const isHigh = s.cpu_utilisation >= 0.7;
        return (
          <div className="flex items-center space-x-2 font-mono">
            <div className="w-16 bg-canvas-dark rounded-full h-1.5 overflow-hidden border border-canvas-border">
              <div
                className={`h-full rounded-full ${isHigh ? "bg-rose-500" : "bg-cyan-400"}`}
                style={{ width: `${Math.min(100, s.cpu_utilisation * 100)}%` }}
              />
            </div>
            <span className={isHigh ? "text-rose-400 font-bold" : "text-text-primary"}>
              {pct}%
            </span>
          </div>
        );
      },
      align: "left",
      width: "150px",
    },
    {
      key: "memory_utilisation",
      header: "Memory Utilization",
      render: (s) => {
        const pct = (s.memory_utilisation * 100).toFixed(1);
        return (
          <div className="flex items-center space-x-2 font-mono">
            <div className="w-16 bg-canvas-dark rounded-full h-1.5 overflow-hidden border border-canvas-border">
              <div
                className="h-full rounded-full bg-blue-400"
                style={{ width: `${Math.min(100, s.memory_utilisation * 100)}%` }}
              />
            </div>
            <span className="text-text-primary">{pct}%</span>
          </div>
        );
      },
      align: "left",
      width: "150px",
    },
    {
      key: "request_rate",
      header: "Throughput",
      render: (s) => (
        <span className="font-mono text-text-primary font-bold">
          {s.request_rate.toFixed(1)}{" "}
          <span className="text-text-muted text-[10px] font-normal">req/s</span>
        </span>
      ),
      align: "right",
      width: "120px",
    },
    {
      key: "p95_latency",
      header: "P95 Latency",
      render: (s) => {
        const isViolated = s.p95_latency > 200;
        return (
          <span className={`font-mono font-bold ${isViolated ? "text-rose-400" : "text-text-primary"}`}>
            {s.p95_latency.toFixed(1)}{" "}
            <span className="text-text-muted text-[10px] font-normal">ms</span>
          </span>
        );
      },
      align: "right",
      width: "120px",
    },
    {
      key: "error_rate",
      header: "Error Rate",
      render: (s) => (
        <span className="font-mono text-text-muted">
          {(s.error_rate * 100).toFixed(2)}%
        </span>
      ),
      align: "right",
      width: "100px",
    },
  ];

  if (loading) return <LoadingState message="Aggregating live microservices telemetry..." />;
  if (error && services.length === 0) return <ErrorState message={error} onRetry={() => loadData(true)} />;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Executive Overview & Cluster Telemetry"
        subtitle="Real-time Prometheus telemetry, bottleneck prioritization scores, and autonomous scaling decisions across the Online Boutique microservices application."
        badge={
          <StatusBadge
            status={`PHASE: ${selectedPhase}`}
            variant="purple"
            pulse
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
              <span>{evaluating ? "Evaluating..." : "Trigger Decision Cycle"}</span>
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
              All scaling recommendations are algorithmic dry-runs verified against safety invariants. Kubernetes cluster mutations remain completely inhibited.
            </p>
          </div>
        </div>
        <Link
          to="/scaling"
          className="flex items-center space-x-1 text-xs text-amber-400 hover:text-amber-300 font-medium whitespace-nowrap self-end sm:self-center"
        >
          <span>Actuator Audit Log</span>
          <ExternalLink size={12} />
        </Link>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <MetricCard
          title="Microservices"
          value={totalServicesCount}
          unit="active"
          variant="cyan"
          icon={Boxes}
          subtext="Online Boutique"
          to="/services"
        />
        <MetricCard
          title="Healthy Services"
          value={`${healthyServicesCount}/${totalServicesCount}`}
          variant={healthyServicesCount === totalServicesCount ? "emerald" : "amber"}
          icon={CheckCircle2}
          subtext="Telemetry responsive"
          to="/services"
        />
        <MetricCard
          title="Active Bottleneck"
          value={bottleneckService || "None"}
          variant={bottleneckService ? "rose" : "emerald"}
          icon={Flame}
          subtext={bottleneckService ? "Prioritized for scale-up" : "All services nominal"}
          to="/bottlenecks"
        />
        <MetricCard
          title="Total Throughput"
          value={totalThroughput.toFixed(1)}
          unit="req/s"
          variant="cyan"
          icon={Activity}
          subtext="Aggregated rate"
          to="/services"
        />
        <MetricCard
          title="Cluster P95 Latency"
          value={averageLatency.toFixed(1)}
          unit="ms"
          variant={averageLatency > 200 ? "rose" : "blue"}
          icon={Zap}
          subtext="SLA Boundary: \u2264200ms"
          to="/services"
        />
        <MetricCard
          title="DPBPS Decisions"
          value={`${pipeline?.scale_up_count ?? 0} Up / ${pipeline?.hold_count ?? 0} Hold`}
          variant="purple"
          icon={Brain}
          subtext={`${pipeline?.scale_down_count ?? 0} Scale-Down`}
          to="/intelligence"
        />
      </div>

      {/* Performance Monitoring Section */}
      <div className="bg-canvas-card border border-canvas-border rounded-xl p-5 shadow-card space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-canvas-border">
          <SectionHeader
            title="Live Performance Stream"
            subtitle="Real-time multi-cycle metrics collected from Prometheus and Kubernetes Metrics Server"
            icon={Activity}
            className="border-b-0 mb-0 py-0"
          />

          {/* Metric Selector Tabs */}
          <div className="flex items-center space-x-1.5 p-1 rounded-lg bg-canvas-dark border border-canvas-border text-xs self-start sm:self-auto font-medium">
            <button
              onClick={() => setChartMetric("throughput")}
              className={`px-3 py-1 rounded-md transition-colors ${
                chartMetric === "throughput"
                  ? "bg-cyan-500/20 text-cyan-400 font-semibold shadow-sm"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              Throughput (req/s)
            </button>
            <button
              onClick={() => setChartMetric("latency")}
              className={`px-3 py-1 rounded-md transition-colors ${
                chartMetric === "latency"
                  ? "bg-blue-500/20 text-blue-400 font-semibold shadow-sm"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              P95 Latency (ms)
            </button>
            <button
              onClick={() => setChartMetric("cpu")}
              className={`px-3 py-1 rounded-md transition-colors ${
                chartMetric === "cpu"
                  ? "bg-purple-500/20 text-purple-400 font-semibold shadow-sm"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              CPU & Memory (%)
            </button>
          </div>
        </div>

        {/* Chart Canvas */}
        <div className="h-64 w-full">
          {history.length === 0 ? (
            <div className="h-full flex items-center justify-center text-xs text-text-muted italic">
              Collecting initial telemetry stream samples...
            </div>
          ) : chartMetric === "cpu" ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={services} margin={{ top: 10, right: 10, left: -20, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" vertical={false} />
                <XAxis
                  dataKey="name"
                  stroke="#6b7280"
                  fontSize={10}
                  tickLine={false}
                  angle={-25}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis stroke="#6b7280" fontSize={10} unit="%" domain={[0, 100]} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload as ServiceInfo;
                      return (
                        <div className="bg-canvas-card border border-canvas-border rounded-lg p-2.5 shadow-xl text-xs font-mono">
                          <p className="font-sans font-bold text-text-primary mb-1">{data.name}</p>
                          <p className="text-cyan-400">CPU: {(data.cpu_utilisation * 100).toFixed(1)}%</p>
                          <p className="text-blue-400">Memory: {(data.memory_utilisation * 100).toFixed(1)}%</p>
                          <p className="text-text-muted text-[10px] mt-1">Replicas: {data.ready_replicas}</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Bar dataKey={(s: ServiceInfo) => parseFloat((s.cpu_utilisation * 100).toFixed(1))} name="CPU %" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                <Bar dataKey={(s: ServiceInfo) => parseFloat((s.memory_utilisation * 100).toFixed(1))} name="Memory %" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <ReferenceLine y={70} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: "CPU Trigger (70%)", fill: "#f59e0b", fontSize: 10 }} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="streamGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="5%"
                      stopColor={chartMetric === "throughput" ? "#06b6d4" : "#3b82f6"}
                      stopOpacity={0.3}
                    />
                    <stop
                      offset="95%"
                      stopColor={chartMetric === "throughput" ? "#06b6d4" : "#3b82f6"}
                      stopOpacity={0.0}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" vertical={false} />
                <XAxis dataKey="time" stroke="#6b7280" fontSize={10} tickLine={false} />
                <YAxis
                  stroke="#6b7280"
                  fontSize={10}
                  unit={chartMetric === "throughput" ? " r/s" : " ms"}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="bg-canvas-card border border-canvas-border rounded-lg p-2.5 shadow-xl text-xs font-mono">
                          <p className="text-text-muted text-[10px] mb-1 font-sans">{label}</p>
                          <p className={chartMetric === "throughput" ? "text-cyan-400 font-bold" : "text-blue-400 font-bold"}>
                            {chartMetric === "throughput"
                              ? `Total Throughput: ${payload[0].value} req/s`
                              : `Average P95 Latency: ${payload[0].value} ms`}
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey={chartMetric === "throughput" ? "throughput" : "avgLatency"}
                  stroke={chartMetric === "throughput" ? "#06b6d4" : "#3b82f6"}
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#streamGrad)"
                />
                {chartMetric === "latency" && (
                  <ReferenceLine
                    y={200}
                    stroke="#ef4444"
                    strokeDasharray="4 2"
                    label={{ value: "SLA (200ms)", fill: "#ef4444", fontSize: 10 }}
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Microservice Health Overview Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <SectionHeader
            title="Online Boutique Microservices Health & Status"
            subtitle="Click any row to inspect deep service telemetry and call dependencies"
            icon={Boxes}
            className="border-b-0 mb-0 py-0"
          />
          <Link
            to="/services"
            className="text-xs text-cyan-400 hover:text-cyan-300 font-medium flex items-center space-x-1"
          >
            <span>Full Inventory View</span>
            <ExternalLink size={12} />
          </Link>
        </div>

        <DataTable
          data={services}
          columns={serviceColumns}
          keyExtractor={(s) => s.id}
          onRowClick={() => navigate("/services")}
          searchPlaceholder="Search services by name..."
        />
      </div>

      {/* Bottom Grid: Deployment Phase Controls & Infrastructure Health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Deployment Phase Controller */}
        <div className="lg:col-span-2 bg-canvas-card border border-canvas-border rounded-xl p-5 shadow-card space-y-4">
          <SectionHeader
            title="CI/CD Deployment Phase Controller"
            subtitle="Modulates DPBPS elasticity weights according to the active deployment stage"
            icon={Layers}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {DEPLOYMENT_PHASES.map((p) => {
              const isSelected = selectedPhase === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => handlePhaseChange(p.id)}
                  className={`p-3.5 rounded-xl border text-left transition-all ${
                    isSelected
                      ? "bg-purple-500/10 border-purple-500/50 shadow-[0_0_15px_rgba(139,92,246,0.15)]"
                      : "bg-canvas-dark border-canvas-border hover:bg-canvas-hover"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-semibold text-xs text-text-primary">{p.label}</span>
                    {isSelected ? (
                      <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
                    ) : (
                      <Radio size={13} className="text-text-muted" />
                    )}
                  </div>
                  <p className="text-[11px] text-text-secondary leading-tight">{p.desc}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Infrastructure Health Status */}
        <div className="bg-canvas-card border border-canvas-border rounded-xl p-5 shadow-card space-y-3 text-xs">
          <SectionHeader
            title="Infrastructure Components"
            subtitle="Verified connectivity to control plane systems"
            icon={Server}
          />

          <div className="space-y-2.5 pt-1 font-mono">
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
              <span className="text-text-secondary font-sans text-xs">FastAPI Backend</span>
              <StatusBadge status={health?.status === "ok" ? "CONNECTED" : "DISCONNECTED"} size="xs" />
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
              <span className="text-text-secondary font-sans text-xs">Kubernetes API (Docker Desktop)</span>
              <StatusBadge status={health?.kubernetes_connected ? "CONNECTED" : "DISCONNECTED"} size="xs" />
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
              <span className="text-text-secondary font-sans text-xs">Prometheus Server</span>
              <StatusBadge status={health?.prometheus_connected ? "READY" : "NO_DATA"} size="xs" />
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
              <span className="text-text-secondary font-sans text-xs">OpenTelemetry Collector</span>
              <StatusBadge status="ACTIVE" label="DAEMONSET" variant="cyan" size="xs" />
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
              <span className="text-text-secondary font-sans text-xs">Scaling Actuator</span>
              <StatusBadge status="DRY_RUN" label="DRY_RUN" variant="amber" size="xs" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
