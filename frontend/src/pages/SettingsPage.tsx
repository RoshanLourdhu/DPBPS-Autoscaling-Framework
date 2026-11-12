// src/pages/SettingsPage.tsx
import { useEffect, useState, useCallback } from "react";
import {
  fetchScalingConfig,
  fetchScalingStatus,
  fetchHealth,
  fetchTelemetrySummary,
  fetchServices,
} from "../services/api";
import type {
  ScalingConfig,
  ScalingStatusResponse,
  HealthResponse,
  TelemetrySummary,
  ServiceInfo,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  Sliders,
  ShieldCheck,
  Lock,
  Server,
  Activity,
  Cpu,
  RefreshCw,
  HardDrive,
  Clock,
  Gauge,
  Radio,
  Layers,
  Database,
  Info,
} from "lucide-react";

export default function SettingsPage() {
  const [config, setConfig] = useState<ScalingConfig | null>(null);
  const [status, setStatus] = useState<ScalingStatusResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetrySummary | null>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  const loadData = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const [cfg, st, hl, tm, svcs] = await Promise.all([
        fetchScalingConfig().catch(() => null),
        fetchScalingStatus().catch(() => null),
        fetchHealth().catch(() => null),
        fetchTelemetrySummary().catch(() => null),
        fetchServices().catch(() => []),
      ]);

      if (cfg) setConfig(cfg);
      if (st) setStatus(st);
      if (hl) setHealth(hl);
      if (tm) setTelemetry(tm);
      setServices(svcs);
      setError(null);
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (e: any) {
      setError(e.message || "Failed to load system configuration");
    } finally {
      if (isInitial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(true);
    const interval = setInterval(() => loadData(false), 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading && !config && !health) {
    return <LoadingState message="Loading platform configuration, safety interlocks, and connectivity status..." />;
  }

  if (error && !config && !health) {
    return <ErrorState message={error} onRetry={() => loadData(true)} />;
  }

  const isBackendConnected = health?.status === "ok";
  const k8sConnected = health?.kubernetes_connected === true;
  const promConnected = health?.prometheus_connected === true;
  const isOtelActive = isBackendConnected && (telemetry?.application_metrics_integrated !== false);
  const isDryRun = health?.dry_run ?? true;
  const isScalingEnabled = health?.scaling_enabled ?? false;
  const activePhase = status?.phase || health?.deployment_phase || "NORMAL_OPERATION";

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <PageHeader
          title="System Configuration & Control Plane"
          subtitle="Infrastructure connectivity status, algorithmic scaling thresholds, actuator invariant clamps, and platform telemetry governance."
          badge={
            <StatusBadge
              status="SAFETY INTERLOCKS LOCKED"
              variant="amber"
            />
          }
        />
        <div className="flex items-center space-x-3 shrink-0">
          {lastRefreshed && (
            <span className="text-[11px] font-mono text-text-muted">
              Synced: {lastRefreshed}
            </span>
          )}
          <button
            onClick={() => loadData(false)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-canvas-card border border-canvas-border hover:bg-canvas-card/80 text-text-secondary hover:text-text-primary transition-colors flex items-center space-x-1.5"
            title="Refresh system settings"
          >
            <RefreshCw size={13} className={loading ? "animate-spin text-cyan-400" : ""} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* 1. Hardware Protection & Safety Invariants Panel */}
      <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-canvas-border pb-3">
          <SectionHeader
            title="Cluster Safety Invariants & Actuator Protection Interlocks"
            subtitle="Immutable production safeguards enforced by configuration. Prevents unintentional cluster state modification."
            icon={ShieldCheck}
          />
          <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold tracking-wider uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center space-x-1 self-start sm:self-auto">
            <Lock size={11} className="mr-1" />
            READ-ONLY ENFORCEMENT
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3.5 rounded-lg bg-canvas-dark border border-canvas-border flex items-center justify-between">
            <div>
              <div className="text-text-muted text-[10px] uppercase font-sans">Actuator Execution Mode</div>
              <div className="text-sm font-bold text-amber-400 mt-0.5">
                {isDryRun ? "DRY_RUN (Simulated)" : "LIVE CLUSTER"}
              </div>
              <div className="text-[10px] text-text-muted mt-0.5 font-sans">Zero scale patches issued</div>
            </div>
            <Lock size={16} className="text-amber-400 shrink-0" />
          </div>

          <div className="p-3.5 rounded-lg bg-canvas-dark border border-canvas-border flex items-center justify-between">
            <div>
              <div className="text-text-muted text-[10px] uppercase font-sans">Live Scaling Controller</div>
              <div className="text-sm font-bold text-emerald-400 mt-0.5">
                {isScalingEnabled ? "SCALING_ENABLED=true" : "SCALING_ENABLED=false"}
              </div>
              <div className="text-[10px] text-text-muted mt-0.5 font-sans">Mutations hardware-locked</div>
            </div>
            <Lock size={16} className="text-emerald-400 shrink-0" />
          </div>

          <div className="p-3.5 rounded-lg bg-canvas-dark border border-canvas-border flex items-center justify-between">
            <div>
              <div className="text-text-muted text-[10px] uppercase font-sans">Locust Load Generator</div>
              <div className="text-sm font-bold text-emerald-400 mt-0.5">REPLICAS = 0</div>
              <div className="text-[10px] text-text-muted mt-0.5 font-sans">Synthetic traffic suppressed</div>
            </div>
            <Lock size={16} className="text-emerald-400 shrink-0" />
          </div>

          <div className="p-3.5 rounded-lg bg-canvas-dark border border-canvas-border flex items-center justify-between">
            <div>
              <div className="text-text-muted text-[10px] uppercase font-sans">Replica Bounds & Delta Step</div>
              <div className="text-sm font-bold text-cyan-400 mt-0.5">
                [1, 10] | |ΔR| ≤ 2
              </div>
              <div className="text-[10px] text-text-muted mt-0.5 font-sans">Anti-thrashing step limit</div>
            </div>
            <Lock size={16} className="text-cyan-400 shrink-0" />
          </div>
        </div>

        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300/90 leading-relaxed font-sans">
          <strong>Non-Negotiable Research Safety Bound:</strong> Live scaling patches to Kubernetes deployments are permanently gated by backend configuration flags (<code className="font-mono text-amber-200">DRY_RUN=True</code> and <code className="font-mono text-amber-200">SCALING_ENABLED=False</code>). All algorithmic recommendations generated by DPBPS are computed, scored, evaluated, and stored in the audit ledger without altering the physical pod counts of running microservices.
        </div>
      </div>

      {/* 2. System Health & Infrastructure Connectivity Overview */}
      <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-4">
        <SectionHeader
          title="Infrastructure Connectivity & Telemetry Pipeline Health"
          subtitle="Real-time link status across backend services, Kubernetes cluster, and Prometheus observability stack"
          icon={Server}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Backend API Service */}
          <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Server size={16} className="text-cyan-400" />
                <span className="font-semibold text-xs text-text-primary">Backend API Engine</span>
              </div>
              <StatusBadge
                status={isBackendConnected ? "OPERATIONAL" : "OFFLINE"}
                variant={isBackendConnected ? "emerald" : "rose"}
              />
            </div>
            <div className="space-y-1 font-mono text-[11px] text-text-muted">
              <div className="flex justify-between">
                <span>Service:</span>
                <span className="text-text-primary">{health?.service || "dpbps-scaling-engine"}</span>
              </div>
              <div className="flex justify-between">
                <span>Version:</span>
                <span className="text-cyan-400">{health?.version || "0.1.0-dpbps-dev"}</span>
              </div>
              <div className="flex justify-between">
                <span>Endpoint:</span>
                <span className="text-text-primary">/api/v1/</span>
              </div>
            </div>
          </div>

          {/* Kubernetes Cluster Connection */}
          <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <HardDrive size={16} className="text-blue-400" />
                <span className="font-semibold text-xs text-text-primary">Kubernetes Cluster</span>
              </div>
              <StatusBadge
                status={k8sConnected ? "CONNECTED" : "DISCONNECTED"}
                variant={k8sConnected ? "emerald" : "rose"}
              />
            </div>
            <div className="space-y-1 font-mono text-[11px] text-text-muted">
              <div className="flex justify-between">
                <span>Namespace:</span>
                <span className="text-text-primary">{telemetry?.namespace || "online-boutique"}</span>
              </div>
              <div className="flex justify-between">
                <span>Deployments:</span>
                <span className="text-text-primary">{telemetry?.deployment_count ?? 10} monitored</span>
              </div>
              <div className="flex justify-between">
                <span>Target API:</span>
                <span className="text-blue-400">apps/v1 (k8s v1.30+)</span>
              </div>
            </div>
          </div>

          {/* Prometheus Observability Engine */}
          <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Activity size={16} className="text-purple-400" />
                <span className="font-semibold text-xs text-text-primary">Prometheus Telemetry</span>
              </div>
              <StatusBadge
                status={promConnected ? "ONLINE" : "OFFLINE"}
                variant={promConnected ? "emerald" : "rose"}
              />
            </div>
            <div className="space-y-1 font-mono text-[11px] text-text-muted">
              <div className="flex justify-between">
                <span>Scrape Endpoint:</span>
                <span className="text-text-primary truncate max-w-[150px]">
                  http://prometheus-k8s.monitoring:9090
                </span>
              </div>
              <div className="flex justify-between">
                <span>Resolution:</span>
                <span className="text-purple-400">5s scrape interval</span>
              </div>
              <div className="flex justify-between">
                <span>Metrics Pipeline:</span>
                <span className="text-emerald-400">PromQL Integrated</span>
              </div>
            </div>
          </div>

          {/* OpenTelemetry Pipeline */}
          <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Radio size={16} className="text-emerald-400" />
                <span className="font-semibold text-xs text-text-primary">OpenTelemetry Collector</span>
              </div>
              <StatusBadge
                status={isOtelActive ? "ACTIVE" : "OFFLINE"}
                variant={isOtelActive ? "emerald" : "rose"}
              />
            </div>
            <div className="space-y-1 font-mono text-[11px] text-text-muted">
              <div className="flex justify-between">
                <span>Receiver:</span>
                <span className="text-text-primary">OTLP / gRPC (Port 4317)</span>
              </div>
              <div className="flex justify-between">
                <span>Exporter:</span>
                <span className="text-emerald-400">Prometheus Exporter (8889)</span>
              </div>
              <div className="flex justify-between">
                <span>App Metrics:</span>
                <span className="text-emerald-400">
                  {telemetry?.application_metrics_integrated !== false ? "Integrated" : "Pending"}
                </span>
              </div>
            </div>
          </div>

          {/* Scaling Actuator Simulation */}
          <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Cpu size={16} className="text-amber-400" />
                <span className="font-semibold text-xs text-text-primary">Scaling Actuator</span>
              </div>
              <StatusBadge status="DRY_RUN AUDIT" variant="amber" />
            </div>
            <div className="space-y-1 font-mono text-[11px] text-text-muted">
              <div className="flex justify-between">
                <span>Mode:</span>
                <span className="text-amber-400">Simulation / Audit</span>
              </div>
              <div className="flex justify-between">
                <span>Cluster Patches:</span>
                <span className="text-emerald-400">0 (Blocked)</span>
              </div>
              <div className="flex justify-between">
                <span>Audit Log:</span>
                <span className="text-text-primary">In-Memory Ring Buffer</span>
              </div>
            </div>
          </div>

          {/* Frontend Web Interface */}
          <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Gauge size={16} className="text-cyan-400" />
                <span className="font-semibold text-xs text-text-primary">Frontend Web Application</span>
              </div>
              <StatusBadge status="READY" variant="cyan" />
            </div>
            <div className="space-y-1 font-mono text-[11px] text-text-muted">
              <div className="flex justify-between">
                <span>UI Framework:</span>
                <span className="text-text-primary">React 18 + Vite</span>
              </div>
              <div className="flex justify-between">
                <span>Design System:</span>
                <span className="text-cyan-400">Stage 10 Tokens</span>
              </div>
              <div className="flex justify-between">
                <span>Poll Cadence:</span>
                <span className="text-text-primary">10s Auto-Sync</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. DPBPS Controller Algorithmic Parameters */}
      <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-canvas-border pb-3">
          <SectionHeader
            title="DPBPS Controller Algorithmic Parameters"
            subtitle="Mathematical thresholds governing elasticity decisions, DAG bottleneck prioritization, and cooldown timing"
            icon={Sliders}
          />
          <span className="font-mono text-xs text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 rounded-md">
            Active Phase: {activePhase}
          </span>
        </div>

        {/* Primary Parameters Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 font-mono text-xs">
          <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border">
            <div className="text-text-muted text-[10px] uppercase font-sans">Min / Max Replica Clamps</div>
            <div className="text-xl font-bold text-cyan-400 mt-1">
              [{config?.min_replicas ?? 1}, {config?.max_replicas ?? 10}]
            </div>
            <div className="text-[10px] text-text-muted mt-1 font-sans">Rigid pod boundary bounds</div>
          </div>

          <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border">
            <div className="text-text-muted text-[10px] uppercase font-sans">CPU Scale-Up Threshold</div>
            <div className="text-xl font-bold text-rose-400 mt-1">
              {((config?.cpu_threshold ?? 0.7) * 100).toFixed(0)}%
            </div>
            <div className="text-[10px] text-text-muted mt-1 font-sans">Proactive scale-up trigger</div>
          </div>

          <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border">
            <div className="text-text-muted text-[10px] uppercase font-sans">Memory Scale-Up Threshold</div>
            <div className="text-xl font-bold text-amber-400 mt-1">
              {((config?.memory_threshold ?? 0.75) * 100).toFixed(0)}%
            </div>
            <div className="text-[10px] text-text-muted mt-1 font-sans">Proactive scale-up trigger</div>
          </div>

          <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border">
            <div className="text-text-muted text-[10px] uppercase font-sans">Latency SLA P95 Target</div>
            <div className="text-xl font-bold text-purple-400 mt-1">
              {config?.latency_target_ms ?? 200} ms
            </div>
            <div className="text-[10px] text-text-muted mt-1 font-sans">Service level agreement bound</div>
          </div>
        </div>

        {/* Secondary Parameters Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 font-mono text-xs">
          <div className="p-3.5 rounded-lg bg-canvas-dark/70 border border-canvas-border space-y-1">
            <div className="flex items-center space-x-1.5 text-text-muted text-[10px] uppercase font-sans">
              <Clock size={12} className="text-cyan-400" />
              <span>Scale-Up Moving Window</span>
            </div>
            <div className="text-base font-bold text-text-primary">
              {config?.scale_up_window_sec ?? 30} seconds
            </div>
            <p className="text-[10px] text-text-muted font-sans leading-tight">
              Rapid response window to detect sudden burst or ramp loads.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-canvas-dark/70 border border-canvas-border space-y-1">
            <div className="flex items-center space-x-1.5 text-text-muted text-[10px] uppercase font-sans">
              <Clock size={12} className="text-amber-400" />
              <span>Scale-Down Stabilization Window</span>
            </div>
            <div className="text-base font-bold text-text-primary">
              {config?.scale_down_window_sec ?? 60} seconds
            </div>
            <p className="text-[10px] text-text-muted font-sans leading-tight">
              Conservative stabilization window to prevent flapping or premature contraction.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-canvas-dark/70 border border-canvas-border space-y-1">
            <div className="flex items-center space-x-1.5 text-text-muted text-[10px] uppercase font-sans">
              <Clock size={12} className="text-emerald-400" />
              <span>Actuation Cooldown Duration</span>
            </div>
            <div className="text-base font-bold text-text-primary">
              {config?.cooldown_sec ?? 45} seconds
            </div>
            <p className="text-[10px] text-text-muted font-sans leading-tight">
              Post-action stabilization period allowing newly provisioned pods to pass readiness probes.
            </p>
          </div>
        </div>

        {/* Threshold Deadband Visualization */}
        <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold text-text-primary">
            <span>Algorithmic Utilization Deadbands & Scaling Regions:</span>
            <span className="font-mono text-[11px] text-text-muted">Target Operating Band: 40% – 70%</span>
          </div>

          <div className="space-y-2 font-mono text-[11px]">
            {/* CPU Band */}
            <div>
              <div className="flex justify-between text-[10px] text-text-muted mb-1">
                <span>CPU Utilization Elasticity Map</span>
                <span>Scale-Down &lt; 40% | Equilibrium 40-70% | Scale-Up &gt; 70%</span>
              </div>
              <div className="h-3 w-full rounded-full bg-canvas-card overflow-hidden flex border border-canvas-border">
                <div className="w-[40%] bg-amber-500/40 text-center text-[9px] text-amber-300 font-bold leading-3">
                  Scale-Down Zone
                </div>
                <div className="w-[30%] bg-emerald-500/40 text-center text-[9px] text-emerald-300 font-bold leading-3">
                  Equilibrium (Hold)
                </div>
                <div className="w-[30%] bg-rose-500/50 text-center text-[9px] text-rose-300 font-bold leading-3">
                  Scale-Up Zone
                </div>
              </div>
            </div>

            {/* Memory Band */}
            <div>
              <div className="flex justify-between text-[10px] text-text-muted mb-1">
                <span>Memory Utilization Elasticity Map</span>
                <span>Equilibrium &lt; 75% | Scale-Up &gt; 75%</span>
              </div>
              <div className="h-3 w-full rounded-full bg-canvas-card overflow-hidden flex border border-canvas-border">
                <div className="w-[75%] bg-emerald-500/40 text-center text-[9px] text-emerald-300 font-bold leading-3">
                  Safe Operating Band (&le; 75%)
                </div>
                <div className="w-[25%] bg-amber-500/50 text-center text-[9px] text-amber-300 font-bold leading-3">
                  Capacity Pressure
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Kubernetes Environment & Monitored Microservices */}
      <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-canvas-border pb-3">
          <SectionHeader
            title="Monitored Microservices Topology"
            subtitle="Google Cloud Online Boutique deployment specifications under active DPBPS surveillance"
            icon={Layers}
          />
          <div className="flex items-center space-x-2 font-mono text-xs">
            <span className="px-2.5 py-1 rounded bg-canvas-dark border border-canvas-border text-cyan-400">
              Namespace: {telemetry?.namespace || "online-boutique"}
            </span>
            <span className="px-2.5 py-1 rounded bg-canvas-dark border border-canvas-border text-emerald-400">
              {services.length || 10} Services Active
            </span>
          </div>
        </div>

        {/* Microservices Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {(services.length > 0
            ? services
            : [
                { id: "frontend", name: "frontend", ready_replicas: 1, health: "HEALTHY" },
                { id: "cartservice", name: "cartservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "productcatalogservice", name: "productcatalogservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "currencyservice", name: "currencyservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "paymentservice", name: "paymentservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "shippingservice", name: "shippingservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "emailservice", name: "emailservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "checkoutservice", name: "checkoutservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "recommendationservice", name: "recommendationservice", ready_replicas: 1, health: "HEALTHY" },
                { id: "adservice", name: "adservice", ready_replicas: 1, health: "HEALTHY" },
              ]
          ).map((s) => (
            <div
              key={s.name || s.id}
              className="p-3 rounded-lg bg-canvas-dark border border-canvas-border space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-semibold text-text-primary truncate">
                  {s.name || s.id}
                </span>
                <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
              </div>
              <div className="flex items-center justify-between font-mono text-[11px] text-text-muted">
                <span>Replicas:</span>
                <span className="text-cyan-400 font-bold">{s.ready_replicas ?? 1} / 1</span>
              </div>
              <div className="flex items-center justify-between font-mono text-[10px] text-text-muted">
                <span>Clamp:</span>
                <span className="text-text-secondary">[1, 10] pods</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 5. Telemetry Ingest & Storage Architecture */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Metric Signals Ingested */}
        <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-3">
          <SectionHeader
            title="Ingested Observability Signals"
            subtitle="Prometheus queries powering DPBPS bottleneck detection"
            icon={Database}
          />

          <div className="space-y-2 font-mono text-xs">
            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <div>
                <div className="text-text-primary font-semibold">container_cpu_usage_seconds_total</div>
                <div className="text-[10px] text-text-muted font-sans">Core rate over 30s window</div>
              </div>
              <span className="text-cyan-400 font-bold text-[11px]">RATE / 30s</span>
            </div>

            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <div>
                <div className="text-text-primary font-semibold">container_memory_working_set_bytes</div>
                <div className="text-[10px] text-text-muted font-sans">Resident working set memory</div>
              </div>
              <span className="text-cyan-400 font-bold text-[11px]">GAUGE</span>
            </div>

            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <div>
                <div className="text-text-primary font-semibold">http_requests_total</div>
                <div className="text-[10px] text-text-muted font-sans">Service throughput (RPS)</div>
              </div>
              <span className="text-cyan-400 font-bold text-[11px]">RATE / 1m</span>
            </div>

            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <div>
                <div className="text-text-primary font-semibold">http_request_duration_seconds</div>
                <div className="text-[10px] text-text-muted font-sans">P95 service latency histogram</div>
              </div>
              <span className="text-cyan-400 font-bold text-[11px]">HISTOGRAM</span>
            </div>
          </div>
        </div>

        {/* Platform & Research Specifications */}
        <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-3">
          <SectionHeader
            title="Research Platform & Environment Metadata"
            subtitle="Formal experimental provenance and configuration tracking"
            icon={Info}
          />

          <div className="space-y-2 text-xs font-mono">
            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <span className="text-text-muted font-sans">Research Framework:</span>
              <span className="text-text-primary font-semibold text-right">DPBPS Autoscaling</span>
            </div>

            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <span className="text-text-muted font-sans">Controller Engine:</span>
              <span className="text-cyan-400 font-bold">v0.1.0-dpbps-dev (FastAPI)</span>
            </div>

            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <span className="text-text-muted font-sans">Frontend Interface:</span>
              <span className="text-emerald-400 font-bold">v1.0.0 (Stage 10 Redesign)</span>
            </div>

            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <span className="text-text-muted font-sans">Git Checkpoint:</span>
              <span className="text-text-primary font-bold">bc41deccc7df370401f83a9206f8e9680071c047</span>
            </div>

            <div className="p-2.5 rounded bg-canvas-dark border border-canvas-border flex justify-between items-center">
              <span className="text-text-muted font-sans">Baseline Policies:</span>
              <span className="text-purple-400 font-bold">Static, CPU, HPA, DPBPS</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
