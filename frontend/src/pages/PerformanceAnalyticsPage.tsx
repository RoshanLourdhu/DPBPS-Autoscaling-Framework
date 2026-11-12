// src/pages/PerformanceAnalyticsPage.tsx
import { useState, useMemo } from "react";
import {
  HISTORICAL_EXPERIMENTS,
  STAGE_9_POLICIES,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  BarChart3,
  TrendingUp,
  ShieldCheck,
  Award,
  AlertTriangle,
  Clock,
  Layers,
  Sparkles,
} from "lucide-react";

const EVALUATION_PLOTS = [
  {
    id: "01",
    name: "Workload Throughput Comparison (E01–E06)",
    file: "01_workload_throughput_comparison.png",
    metric: "Requests per second (RPS)",
    insight: "Demonstrates throughput across all 6 dynamic profiles, peaking at 83.57 RPS during the E03 sudden spike.",
  },
  {
    id: "02",
    name: "End-to-End Latency Percentiles (P50, P95, P99)",
    file: "02_latency_percentiles_comparison.png",
    metric: "Latency in milliseconds",
    insight: "E02 stepped ramp induced highest tail latency (P95 = 1,112.7 ms) due to cascading bottleneck queuing.",
  },
  {
    id: "03",
    name: "CPU Utilization Across Workload Profiles",
    file: "03_cpu_utilization_across_profiles.png",
    metric: "Normalized core utilization (%)",
    insight: "Frontend and checkoutservice hit saturation early; productcatalogservice showed sustained memory pressure.",
  },
  {
    id: "04",
    name: "Memory Utilization Across Workload Profiles",
    file: "04_memory_utilization_across_profiles.png",
    metric: "Working set MiB / limits",
    insight: "Memory utilization remained highly stable (<65%) across all microservices, confirming CPU-bound bottlenecks.",
  },
  {
    id: "05",
    name: "Total Scale-Up Count by Policy",
    file: "05_scale_up_count_by_policy.png",
    metric: "Scale-up decision events",
    insight: "HPA generated 34 scale-ups (excessive); DPBPS generated 27 targeted scale-ups matching CPU-threshold count.",
  },
  {
    id: "06",
    name: "Total Scale-Down Count by Policy",
    file: "06_scale_down_count_by_policy.png",
    metric: "Scale-down decision events",
    insight: "CPU-threshold triggered 3 premature downscales including a floor breach; DPBPS held 0 premature downscales.",
  },
  {
    id: "07",
    name: "Equilibrium Hold Decisions by Policy",
    file: "07_hold_decision_count_by_policy.png",
    metric: "Hold decisions count",
    insight: "DPBPS maintained 991 holds (94.4%), confirming high decision equilibrium without oscillatory flapping.",
  },
  {
    id: "08",
    name: "Recommendation Frequency Distribution",
    file: "08_recommendation_frequency_comparison.png",
    metric: "Action distribution %",
    insight: "DPBPS scaling frequency was 2.57%, achieving optimal elasticity with the lowest disruption to cluster pods.",
  },
  {
    id: "09",
    name: "First Scale-Up Response Time Comparison",
    file: "09_first_scale_up_time_comparison.png",
    metric: "Seconds from onset to scale-up",
    insight: "DPBPS detected E02 surge in 10s (vs 160s for CPU threshold and 150s for HPA), cutting detection lag by 93.7%.",
  },
  {
    id: "10",
    name: "Scaling Decision Stability Index",
    file: "10_decision_stability_comparison.png",
    metric: "Hold / Total Decisions %",
    insight: "DPBPS scored 94.4% stability index, avoiding the 2 severe flapping events experienced by CPU-threshold in E06.",
  },
  {
    id: "11",
    name: "DPBPS Microservice Bottleneck Prioritization",
    file: "11_dpbps_service_prioritization.png",
    metric: "Targeted scaling distribution %",
    insight: "96.3% of DPBPS scale-ups targeted frontend & checkout; 0 misdirected scale-ups occurred to leaf services.",
  },
  {
    id: "12",
    name: "Experiment-Wise Policy Decision Distribution",
    file: "12_experiment_wise_policy_comparison.png",
    metric: "Decisions per experiment",
    insight: "Side-by-side decision distribution across E01 through E06 confirming consistent behavior under all traffic shapes.",
  },
];

export default function PerformanceAnalyticsPage() {
  const [selectedPolicyId, setSelectedPolicyId] = useState<string>("ALL");
  const [selectedPlotId, setSelectedPlotId] = useState<string>("01");
  const [activeTab, setActiveTab] = useState<"POLICIES" | "EXPERIMENTS" | "CAVEATS">("POLICIES");

  // Filtered policies
  const filteredPolicies = useMemo(() => {
    if (selectedPolicyId === "ALL") return STAGE_9_POLICIES;
    return STAGE_9_POLICIES.filter((p) => p.policyId === selectedPolicyId);
  }, [selectedPolicyId]);

  // Chart data: Stage 9 Policy Decision Distribution
  const policyDistributionData = useMemo(() => {
    return STAGE_9_POLICIES.map((p) => ({
      name: p.policyName.replace(" (Control)", "").replace(" Reactive", "").replace(" (Proposed Framework)", ""),
      hold: p.holdCount,
      scaleUp: p.scaleUpCount,
      scaleDown: p.scaleDownCount,
      stability: p.decisionStability,
    }));
  }, []);

  // Chart data: Stage 9 Detection Time Comparison (E02 and E03)
  const detectionVelocityData = useMemo(() => {
    return [
      {
        policy: "Static",
        e02: 0,
        e03: 0,
        note: "Never scales",
      },
      {
        policy: "CPU-Threshold",
        e02: 160,
        e03: 80,
        note: "Dual-watermark lag",
      },
      {
        policy: "Kubernetes HPA",
        e02: 150,
        e03: 70,
        note: "Proportional lag",
      },
      {
        policy: "DPBPS (Proposed)",
        e02: 10,
        e03: 50,
        note: "Rapid DAG detection",
      },
    ];
  }, []);

  // Chart data: Historical Experiments Throughput & Latency
  const experimentSummaryChartData = useMemo(() => {
    return HISTORICAL_EXPERIMENTS.map((h) => ({
      name: h.profile.replace("_TRAFFIC", "").replace("_INCREASE", "").replace("_SPIKE", "").replace("_HIGH", ""),
      avgRps: h.avgFrontendRps,
      peakRps: h.peakFrontendRps,
      avgP95: h.avgFrontendP95Ms,
      maxP95: h.maxFrontendP95Ms,
      scaleUp: h.scaleUpCount,
      hold: h.holdCount,
      errorRate: h.maxErrorRate * 100,
    }));
  }, []);

  const selectedPlot = EVALUATION_PLOTS.find((p) => p.id === selectedPlotId) || EVALUATION_PLOTS[0];

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <PageHeader
        title="Empirical Performance Analytics & Comparative Scaling Evaluation"
        subtitle="Offline trace-replay evaluation comparing DPBPS against Static, CPU-Threshold, and Kubernetes HPA baselines across 1,050 microservice observations."
        badge={
          <StatusBadge
            status="STAGE 9 COMPARATIVE REPLAY: VERIFIED"
            variant="cyan"
          />
        }
      />

      {/* Dataset Attribution Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-canvas-card border border-canvas-border text-xs font-mono">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-text-muted">DATA SOURCES:</span>
          <span className="px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-300 font-bold">
            Stage 8 Workload Campaign (Live Telemetry)
          </span>
          <span className="px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 font-bold">
            Stage 9 Offline Trace-Replay Engine (Deterministic Replay)
          </span>
        </div>
        <div className="text-text-muted">
          Replay Cycles: <strong className="text-text-primary">1,050 Snapshots</strong>
        </div>
      </div>

      {/* 1. Analytics Overview KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
        <MetricCard
          title="Historical Traces"
          value="1,050"
          unit="snapshots"
          variant="cyan"
          icon={BarChart3}
          subtext="E01–E06 campaigns"
        />
        <MetricCard
          title="Policies Evaluated"
          value="4"
          unit="policies"
          variant="purple"
          icon={Award}
          subtext="Static, CPU, HPA, DPBPS"
        />
        <MetricCard
          title="Mean Workload RPS"
          value="27.9"
          unit="req/s"
          variant="blue"
          icon={TrendingUp}
          subtext="Peak: 83.57 req/s (E03)"
        />
        <MetricCard
          title="Mean P95 Latency"
          value="562.8"
          unit="ms"
          variant="amber"
          icon={Clock}
          subtext="Peak: 4,171.87 ms (E02)"
        />
        <MetricCard
          title="DPBPS Decision Stability"
          value="94.4"
          unit="%"
          variant="emerald"
          icon={ShieldCheck}
          subtext="991 holds / 1,050 cycles"
        />
        <MetricCard
          title="Bottleneck Specificity"
          value="96.3"
          unit="%"
          variant="rose"
          icon={Sparkles}
          subtext="0 misdirected scale-ups"
        />
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center space-x-2 border-b border-canvas-border pb-2 text-xs font-mono">
        <button
          onClick={() => setActiveTab("POLICIES")}
          className={`px-3 py-1.5 rounded-lg transition-colors font-bold ${
            activeTab === "POLICIES"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-text-muted hover:text-text-primary"
          }`}
        >
          1. Comparative Policy Evaluation (Stage 9)
        </button>
        <button
          onClick={() => setActiveTab("EXPERIMENTS")}
          className={`px-3 py-1.5 rounded-lg transition-colors font-bold ${
            activeTab === "EXPERIMENTS"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-text-muted hover:text-text-primary"
          }`}
        >
          2. Historical Workload Profiles (Stage 8)
        </button>
        <button
          onClick={() => setActiveTab("CAVEATS")}
          className={`px-3 py-1.5 rounded-lg transition-colors font-bold flex items-center space-x-1 ${
            activeTab === "CAVEATS"
              ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
              : "text-amber-400 hover:text-amber-300"
          }`}
        >
          <AlertTriangle size={13} />
          <span>3. Research Limitations & Warnings (Stage 9.1)</span>
        </button>
      </div>

      {/* TAB 1: COMPARATIVE POLICY EVALUATION (STAGE 9) */}
      {activeTab === "POLICIES" && (
        <div className="space-y-6">
          {/* Policy Overview Filter */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <SectionHeader
              title="Four-Way Comparative Scaling Policy Matrix (1,050 Evaluations)"
              subtitle="Deterministic offline replay comparing control, single-metric reactive, proportional HPA, and proposed DPBPS"
              icon={Award}
            />

            <div className="flex items-center space-x-1 bg-canvas-dark p-0.5 rounded-lg border border-canvas-border text-xs font-mono">
              <span className="text-text-muted px-2">Filter:</span>
              {(["ALL", "DPBPS", "HPA_STYLE", "CPU_THRESHOLD", "STATIC"] as const).map((pol) => (
                <button
                  key={pol}
                  onClick={() => setSelectedPolicyId(pol)}
                  className={`px-2 py-1 rounded-md transition-colors text-[11px] ${
                    selectedPolicyId === pol
                      ? "bg-canvas-card text-text-primary font-bold shadow-xs border border-canvas-border"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {pol === "ALL" ? "All (4)" : pol.replace("_STYLE", "")}
                </button>
              ))}
            </div>
          </div>

          {/* Comparative Table */}
          <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                    <th className="py-3 px-4 font-semibold">Scaling Policy</th>
                    <th className="py-3 px-3 font-semibold text-center">Category</th>
                    <th className="py-3 px-3 font-semibold text-center">Evaluations</th>
                    <th className="py-3 px-3 font-semibold text-center">Holds (%)</th>
                    <th className="py-3 px-3 font-semibold text-center">Scale Up</th>
                    <th className="py-3 px-3 font-semibold text-center">Scale Down</th>
                    <th className="py-3 px-3 font-semibold text-right">E02 Lag (s)</th>
                    <th className="py-3 px-3 font-semibold text-right">E03 Lag (s)</th>
                    <th className="py-3 px-3 font-semibold text-right">Flapping (E06)</th>
                    <th className="py-3 px-3 font-semibold text-right">Targeting %</th>
                    <th className="py-3 px-3 font-semibold text-right">Leaf Errors</th>
                    <th className="py-3 px-3 font-semibold text-right">Max Replicas</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-canvas-border font-mono">
                  {filteredPolicies.map((p) => {
                    const isProposed = p.category === "PROPOSED";
                    return (
                      <tr
                        key={p.policyId}
                        className={`hover:bg-canvas-dark/30 transition-colors ${
                          isProposed ? "bg-cyan-950/10 font-medium" : ""
                        }`}
                      >
                        <td className="py-3 px-4 font-bold text-text-primary">
                          <div className="flex items-center space-x-1.5">
                            {isProposed && <Sparkles size={13} className="text-cyan-400" />}
                            <span>{p.policyName}</span>
                          </div>
                          <div className="text-[10px] text-text-muted font-normal font-sans line-clamp-1 mt-0.5">
                            {p.description}
                          </div>
                        </td>
                        <td className="py-3 px-3 text-center">
                          <StatusBadge
                            status={p.category}
                            variant={isProposed ? "cyan" : "slate"}
                            size="xs"
                          />
                        </td>
                        <td className="py-3 px-3 text-center text-text-primary">
                          {p.totalEvaluations}
                        </td>
                        <td className="py-3 px-3 text-center text-emerald-400 font-bold">
                          {p.holdCount} ({p.holdPercent.toFixed(1)}%)
                        </td>
                        <td className="py-3 px-3 text-center text-rose-400 font-bold">
                          {p.scaleUpCount}
                        </td>
                        <td className="py-3 px-3 text-center text-amber-400">
                          {p.scaleDownCount}
                        </td>
                        <td className="py-3 px-3 text-right">
                          {p.e02DetectionTimeSec !== null ? (
                            <span className={p.e02DetectionTimeSec <= 15 ? "text-cyan-400 font-bold" : "text-text-muted"}>
                              {p.e02DetectionTimeSec.toFixed(1)}s
                            </span>
                          ) : (
                            <span className="text-text-muted">&infin;</span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-right">
                          {p.e03DetectionTimeSec !== null ? (
                            <span className={p.e03DetectionTimeSec <= 50 ? "text-cyan-400 font-bold" : "text-text-muted"}>
                              {p.e03DetectionTimeSec.toFixed(1)}s
                            </span>
                          ) : (
                            <span className="text-text-muted">&infin;</span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <span className={p.e06FlappingCount > 0 ? "text-rose-400 font-bold" : "text-emerald-400"}>
                            {p.e06FlappingCount}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-right font-bold text-cyan-400">
                          {p.bottleneckTargetingRatio > 0 ? `${p.bottleneckTargetingRatio.toFixed(1)}%` : "N/A"}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <span className={p.misdirectedLeafScaleUps > 0 ? "text-rose-400 font-bold" : "text-emerald-400"}>
                            {p.misdirectedLeafScaleUps}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-right text-text-primary">
                          {p.maxReplicasProposed}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Visual Recharts: Decision Distribution & Detection Lag */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Chart 1: Decision Distribution Breakdown */}
            <div className="rounded-xl border border-canvas-border bg-canvas-card p-4 space-y-3 shadow-card">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider font-mono">
                  Policy Decision Breakdown (Holds vs Scale Actions)
                </h4>
                <span className="text-[10px] font-mono text-cyan-400">1,050 Evaluations Total</span>
              </div>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={policyDistributionData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                    <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111827",
                        borderColor: "#1f293d",
                        borderRadius: "0.5rem",
                        fontSize: "0.75rem",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "5px" }} />
                    <Bar dataKey="hold" name="Hold Decisions" fill="#10b981" stackId="a" />
                    <Bar dataKey="scaleUp" name="Scale-Up" fill="#f43f5e" stackId="a" />
                    <Bar dataKey="scaleDown" name="Scale-Down" fill="#f59e0b" stackId="a" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 2: Detection Latency Comparison */}
            <div className="rounded-xl border border-canvas-border bg-canvas-card p-4 space-y-3 shadow-card">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider font-mono">
                  Detection Lag to First Scale-Up (E02 Gradual vs E03 Spike)
                </h4>
                <span className="text-[10px] font-mono text-cyan-400">Seconds (Lower is Faster)</span>
              </div>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={detectionVelocityData.slice(1)} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                    <XAxis dataKey="policy" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111827",
                        borderColor: "#1f293d",
                        borderRadius: "0.5rem",
                        fontSize: "0.75rem",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "5px" }} />
                    <Bar dataKey="e02" name="E02 Stepped Ramp (s)" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="e03" name="E03 Sudden Surge (s)" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* 12 Publication Plots Gallery */}
          <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-4">
            <SectionHeader
              title="Publication Evaluation Plots Gallery (Stage 9 Research Artifacts)"
              subtitle="Inspect the 12 comparative charts generated from empirical workload experiment records"
              icon={BarChart3}
            />

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 text-xs">
              {EVALUATION_PLOTS.map((plot) => (
                <button
                  key={plot.id}
                  onClick={() => setSelectedPlotId(plot.id)}
                  className={`p-2.5 rounded-lg border text-left transition-colors truncate ${
                    selectedPlotId === plot.id
                      ? "bg-cyan-500/10 border-cyan-500/40 text-cyan-300 font-semibold shadow-xs"
                      : "bg-canvas-dark border-canvas-border text-text-secondary hover:text-text-primary"
                  }`}
                >
                  <span className="font-mono text-[10px] text-cyan-400 block mb-0.5">Plot {plot.id}</span>
                  <span className="truncate block font-mono text-[11px]">{plot.name}</span>
                </button>
              ))}
            </div>

            {/* Plot Details Card */}
            <div className="p-4 rounded-xl bg-canvas-dark border border-canvas-border space-y-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-1">
                <span className="font-bold text-text-primary">
                  Plot {selectedPlot.id}: {selectedPlot.name}
                </span>
                <span className="font-mono text-cyan-400 text-[11px]">
                  results/evaluation/plots/{selectedPlot.file}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono pt-1">
                <div className="text-text-muted">
                  Metric: <strong className="text-text-secondary">{selectedPlot.metric}</strong>
                </div>
                <div className="text-text-muted">
                  Artifact Status: <strong className="text-emerald-400">Generated & Preserved on Disk</strong>
                </div>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed font-sans pt-1">
                {selectedPlot.insight}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: HISTORICAL WORKLOAD PROFILES (STAGE 8) */}
      {activeTab === "EXPERIMENTS" && (
        <div className="space-y-6">
          <SectionHeader
            title="Stage 8 Empirical Workload Campaign Performance (E01–E06)"
            subtitle="Authoritative measurements collected during live Kubernetes cluster benchmarking (Online Boutique namespace)"
            icon={Layers}
          />

          {/* Historical Experiments Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Throughput chart */}
            <div className="rounded-xl border border-canvas-border bg-canvas-card p-4 space-y-3 shadow-card">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider font-mono">
                  Throughput Profile: Average vs Peak RPS
                </h4>
                <span className="text-[10px] font-mono text-cyan-400">Requests / second</span>
              </div>
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={experimentSummaryChartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                    <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111827",
                        borderColor: "#1f293d",
                        borderRadius: "0.5rem",
                        fontSize: "0.75rem",
                      }}
                    />
                    <Bar dataKey="avgRps" name="Average RPS" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="peakRps" name="Peak RPS" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Latency chart */}
            <div className="rounded-xl border border-canvas-border bg-canvas-card p-4 space-y-3 shadow-card">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider font-mono">
                  End-to-End P95 Latency (Mean vs Maximum)
                </h4>
                <span className="text-[10px] font-mono text-rose-400">Milliseconds (ms)</span>
              </div>
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={experimentSummaryChartData} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                    <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111827",
                        borderColor: "#1f293d",
                        borderRadius: "0.5rem",
                        fontSize: "0.75rem",
                      }}
                    />
                    <Bar dataKey="avgP95" name="Average P95 (ms)" fill="#a855f7" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="maxP95" name="Peak P95 (ms)" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Historical Experiment Data Table */}
          <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                    <th className="py-3 px-4 font-semibold">Experiment ID</th>
                    <th className="py-3 px-3 font-semibold">Workload Profile</th>
                    <th className="py-3 px-3 font-semibold text-right">Users</th>
                    <th className="py-3 px-3 font-semibold text-right">Duration</th>
                    <th className="py-3 px-3 font-semibold text-right">Avg RPS</th>
                    <th className="py-3 px-3 font-semibold text-right">Peak RPS</th>
                    <th className="py-3 px-3 font-semibold text-right">Avg P95</th>
                    <th className="py-3 px-3 font-semibold text-right">Peak P95</th>
                    <th className="py-3 px-3 font-semibold text-right">Error Rate</th>
                    <th className="py-3 px-3 font-semibold text-center">Scale Up</th>
                    <th className="py-3 px-3 font-semibold text-center">Holds</th>
                    <th className="py-3 px-3 font-semibold text-center">Bottlenecks</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-canvas-border font-mono">
                  {HISTORICAL_EXPERIMENTS.map((h) => (
                    <tr key={h.id} className="hover:bg-canvas-dark/30">
                      <td className="py-3 px-4 font-bold text-text-primary text-[11px]">
                        {h.id}
                      </td>
                      <td className="py-3 px-3 text-text-secondary">{h.profile}</td>
                      <td className="py-3 px-3 text-right text-text-primary">{h.users}</td>
                      <td className="py-3 px-3 text-right text-text-secondary">{h.durationSeconds}s</td>
                      <td className="py-3 px-3 text-right font-bold text-cyan-400">{h.avgFrontendRps.toFixed(2)}</td>
                      <td className="py-3 px-3 text-right text-text-primary">{h.peakFrontendRps.toFixed(2)}</td>
                      <td className="py-3 px-3 text-right text-text-primary">{h.avgFrontendP95Ms.toFixed(1)} ms</td>
                      <td className="py-3 px-3 text-right text-rose-400">{h.maxFrontendP95Ms.toFixed(1)} ms</td>
                      <td className="py-3 px-3 text-right text-text-secondary">{(h.maxErrorRate * 100).toFixed(2)}%</td>
                      <td className="py-3 px-3 text-center text-rose-400 font-bold">{h.scaleUpCount}</td>
                      <td className="py-3 px-3 text-center text-emerald-400">{h.holdCount}</td>
                      <td className="py-3 px-3 text-center text-amber-400">{h.bottlenecksDetected}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: RESEARCH LIMITATIONS & STAGE 9 WARNINGS */}
      {activeTab === "CAVEATS" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-5 shadow-card space-y-4">
            <div className="flex items-center space-x-3 pb-3 border-b border-amber-500/20">
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <AlertTriangle size={20} />
              </div>
              <div>
                <h3 className="text-base font-bold text-amber-400">
                  Research Validation Caveats & Stage 9 Evaluation Audit Disclosures
                </h3>
                <p className="text-xs text-text-muted mt-0.5">
                  The DPBPS comparative evaluation adheres to strict academic reproducibility principles. The following 6 caveats must not be concealed:
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-sans">
              <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border space-y-2">
                <div className="font-bold text-text-primary flex items-center space-x-2 font-mono">
                  <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                  <span>1. Observation Count Reconciliation (1,050 vs 1,018)</span>
                </div>
                <p className="text-text-secondary leading-relaxed">
                  While exactly 1,050 raw telemetry snapshots were collected across E01–E06 (105 time-steps &times; 10 services), exactly 1,018 evaluations yielded active decisions (991 holds + 27 scale-ups). Exactly 32 observations during E01 cold-start had incomplete Prometheus latency signals and were honestly handled as <code>INSUFFICIENT_TELEMETRY</code>.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border space-y-2">
                <div className="font-bold text-text-primary flex items-center space-x-2 font-mono">
                  <span className="w-2 h-2 rounded-full bg-rose-400"></span>
                  <span>2. CPU-Threshold Baseline Safety Boundary Breach</span>
                </div>
                <p className="text-text-secondary leading-relaxed">
                  During E05 (traffic decrease), the unconstrained CPU-threshold baseline generated a scale-down below the cluster minimum (R_min = 1), exposing the lack of safety clamping in naive watermarking. DPBPS and HPA strictly respected replica bounds.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border space-y-2">
                <div className="font-bold text-text-primary flex items-center space-x-2 font-mono">
                  <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                  <span>3. Bottleneck Specificity Ground-Truth Validation</span>
                </div>
                <p className="text-text-secondary leading-relaxed">
                  The reported 96.3% bottleneck targeting ratio measures scale-ups directed to high-centrality services (<code>frontend</code> and <code>checkoutservice</code>). This was verified via DAG centrality rather than physical thread pool queue depth; multi-node hardware verification remains recommended.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border space-y-2">
                <div className="font-bold text-text-primary flex items-center space-x-2 font-mono">
                  <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                  <span>4. Synchronized Scrape-Window Detection Velocity</span>
                </div>
                <p className="text-text-secondary leading-relaxed">
                  The rapid 10s detection velocity in E02 and 50s in E03 reflect discrete 5-second Prometheus scrape windows. Sub-second streaming telemetry traces would be required to verify real-time millisecond-level responsiveness.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border space-y-2">
                <div className="font-bold text-text-primary flex items-center space-x-2 font-mono">
                  <span className="w-2 h-2 rounded-full bg-purple-400"></span>
                  <span>5. Hold Fraction vs Physical Flapping Stability</span>
                </div>
                <p className="text-text-secondary leading-relaxed">
                  The 94.4% hold fraction indicates mathematical decision equilibrium across time steps. It must not be conflated with temporal pod churn or cluster-level operational stability, which also depend on Kubernetes pod startup times.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-canvas-dark border border-canvas-border space-y-2">
                <div className="font-bold text-text-primary flex items-center space-x-2 font-mono">
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                  <span>6. Offline Trace Replay Scope vs Live Latency Impact</span>
                </div>
                <p className="text-text-secondary leading-relaxed">
                  The comparative evaluation was executed via deterministic offline trace replay (<code>backend/evaluation/</code>). Because live cluster pod scaling was strictly disabled in Stage 8, findings establish algorithmic decision superiority rather than measured latency reduction on live pods.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
