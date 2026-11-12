// src/pages/ExperimentsPage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  fetchWorkloadProfiles,
  fetchExperiments,
  validateExperimentConfig,
  createExperiment,
  HISTORICAL_EXPERIMENTS,
} from "../services/api";
import type {
  WorkloadProfileConfig,
  ExperimentMetadata,
  ExperimentValidationResponse,
  HistoricalExperimentSummary,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import {
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  Sliders,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Activity,
  PlusCircle,
  FileCheck,
  XCircle,
  BarChart3,
  Flame,
  TrendingDown,
  TrendingUp,
  Zap,
  Search,
  CheckSquare,
  Square,
  Sparkles,
  Lock,
  ChevronRight,
  Database,
} from "lucide-react";

export default function ExperimentsPage() {
  const [profiles, setProfiles] = useState<WorkloadProfileConfig[]>([]);
  const [apiExperiments, setApiExperiments] = useState<ExperimentMetadata[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<WorkloadProfileConfig | null>(null);
  const [selectedExperiment, setSelectedExperiment] = useState<HistoricalExperimentSummary | null>(
    HISTORICAL_EXPERIMENTS[3] // Default to Sustained High Traffic (E04)
  );
  const [comparedExpIds, setComparedExpIds] = useState<string[]>(
    HISTORICAL_EXPERIMENTS.map((e) => e.id) // Default all 6 selected for rich comparison
  );
  const [validationResult, setValidationResult] = useState<ExperimentValidationResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");
  const [experimentNotes, setExperimentNotes] = useState<string>("");
  const [creating, setCreating] = useState<boolean>(false);
  const [creationSuccess, setCreationSuccess] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [profileFilter, setProfileFilter] = useState<string>("ALL");

  const loadData = useCallback(async () => {
    setRefreshing(true);
    try {
      const [profs, exps] = await Promise.all([
        fetchWorkloadProfiles().catch(() => []),
        fetchExperiments(50).catch(() => []),
      ]);
      setProfiles(profs);
      setApiExperiments(exps);

      if (profs.length > 0 && !selectedProfile) {
        setSelectedProfile(profs[0]);
      }
      setLastRefreshed(new Date().toLocaleTimeString());
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load experiment resources.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedProfile]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Merge historical verified runs with any newly prepared API records
  const allExperiments = useMemo(() => {
    // Map verified historical runs
    const historicalMapped = HISTORICAL_EXPERIMENTS.map((h) => ({
      isHistorical: true,
      id: h.id,
      profile: h.profile,
      displayName: h.displayName,
      status: h.status,
      duration: h.durationSeconds,
      users: h.users,
      avgRps: h.avgFrontendRps,
      peakRps: h.peakFrontendRps,
      avgP95: h.avgFrontendP95Ms,
      maxP95: h.maxFrontendP95Ms,
      errorRate: h.maxErrorRate * 100,
      scaleUp: h.scaleUpCount,
      scaleDown: h.scaleDownCount,
      hold: h.holdCount,
      bottlenecks: h.bottlenecksDetected,
      createdAt: h.createdAt,
      startedAt: h.startedAt,
      endedAt: h.endedAt,
      notes: h.notes,
      tags: h.tags,
      clusterModified: h.clusterModified,
      actuatorMode: h.actuatorMode,
    }));

    // Map any newly created API experiments that aren't already in historical list
    const apiMapped = apiExperiments
      .filter((ae) => !HISTORICAL_EXPERIMENTS.some((h) => h.id === ae.experiment_id))
      .map((ae) => ({
        isHistorical: false,
        id: ae.experiment_id,
        profile: ae.profile_name,
        displayName: ae.configuration?.display_name || ae.profile_name,
        status: ae.status,
        duration: ae.configuration?.total_duration_seconds || 0,
        users: ae.selected_concurrency,
        avgRps: ae.actual_observed_request_rate ?? null,
        peakRps: null,
        avgP95: null,
        maxP95: null,
        errorRate: null,
        scaleUp: null,
        scaleDown: null,
        hold: null,
        bottlenecks: null,
        createdAt: ae.created_at,
        startedAt: ae.start_timestamp,
        endedAt: ae.end_timestamp,
        notes: ae.notes || "Prepared in local storage",
        tags: ae.tags,
        clusterModified: false,
        actuatorMode: "DRY_RUN",
      }));

    return [...historicalMapped, ...apiMapped];
  }, [apiExperiments]);

  // Filtered experiments for table
  const filteredExperiments = useMemo(() => {
    return allExperiments.filter((exp) => {
      if (statusFilter !== "ALL" && exp.status !== statusFilter) return false;
      if (profileFilter !== "ALL" && exp.profile !== profileFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          exp.id.toLowerCase().includes(q) ||
          exp.profile.toLowerCase().includes(q) ||
          exp.displayName.toLowerCase().includes(q) ||
          exp.notes.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [allExperiments, statusFilter, profileFilter, searchQuery]);

  // Toggle experiment selection for comparison
  const toggleCompare = (id: string) => {
    setComparedExpIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleSelectAllCompare = () => {
    if (comparedExpIds.length === HISTORICAL_EXPERIMENTS.length) {
      setComparedExpIds([]);
    } else {
      setComparedExpIds(HISTORICAL_EXPERIMENTS.map((e) => e.id));
    }
  };

  // Profile icon helper
  const getProfileIcon = (name: string) => {
    switch (name) {
      case "NORMAL_TRAFFIC":
        return <Activity className="h-4 w-4 text-cyan-400" />;
      case "GRADUAL_TRAFFIC_INCREASE":
        return <TrendingUp className="h-4 w-4 text-emerald-400" />;
      case "SUDDEN_TRAFFIC_SPIKE":
        return <Zap className="h-4 w-4 text-amber-400" />;
      case "SUSTAINED_HIGH_TRAFFIC":
        return <Flame className="h-4 w-4 text-rose-400" />;
      case "TRAFFIC_DECREASE":
        return <TrendingDown className="h-4 w-4 text-purple-400" />;
      case "BURSTY_TRAFFIC":
        return <BarChart3 className="h-4 w-4 text-blue-400" />;
      default:
        return <Sliders className="h-4 w-4 text-text-muted" />;
    }
  };

  const handleValidateConfig = async () => {
    if (!selectedProfile) return;
    try {
      const res = await validateExperimentConfig(selectedProfile);
      setValidationResult(res);
    } catch (e: any) {
      setError(`Validation failed: ${e.message}`);
    }
  };

  const handlePrepareExperiment = async () => {
    if (!selectedProfile) return;
    setCreating(true);
    setCreationSuccess(null);
    try {
      const created = await createExperiment({
        profile_name: selectedProfile.profile_name,
        custom_configuration: selectedProfile,
        notes: experimentNotes || `Prepared ${selectedProfile.display_name}`,
        tags: ["stage-10-prepared", selectedProfile.profile_name.toLowerCase()],
      });
      setCreationSuccess(`Experiment record created: ${created.experiment_id} (Status: ${created.status})`);
      setExperimentNotes("");
      await loadData();
    } catch (e: any) {
      setError(`Failed to prepare experiment: ${e.message}`);
    } finally {
      setCreating(false);
    }
  };

  // Comparison dataset
  const comparisonData = useMemo(() => {
    return HISTORICAL_EXPERIMENTS.filter((h) => comparedExpIds.includes(h.id)).map((h) => ({
      name: h.profile.replace("_TRAFFIC", "").replace("_INCREASE", "").replace("_SPIKE", "").replace("_HIGH", ""),
      profile: h.profile,
      id: h.id,
      avgRps: h.avgFrontendRps,
      peakRps: h.peakFrontendRps,
      avgP95: h.avgFrontendP95Ms,
      maxP95: h.maxFrontendP95Ms,
      scaleUp: h.scaleUpCount,
      hold: h.holdCount,
      bottlenecks: h.bottlenecksDetected,
      users: h.users,
      duration: h.durationSeconds,
      errorRate: (h.maxErrorRate * 100).toFixed(2),
    }));
  }, [comparedExpIds]);

  if (loading && profiles.length === 0) {
    return <LoadingState message="Loading workload profiles and historical experiments..." />;
  }

  if (error && profiles.length === 0) {
    return <ErrorState message={error} onRetry={loadData} />;
  }

  return (
    <div className="space-y-8 pb-12">
      {/* Header & Primary Actions */}
      <PageHeader
        title="DPBPS Workload Experiments & Empirical Evaluation"
        subtitle="Reproducible workload profiles, historical execution records, and side-by-side policy performance comparisons."
        badge={
          <StatusBadge
            status="EXPERIMENTS: 6 COMPLETED"
            variant="cyan"
          />
        }
        actions={
          <div className="flex items-center space-x-2">
            <span className="hidden sm:flex items-center space-x-1 text-xs font-mono text-text-muted">
              <Clock size={13} />
              <span>{lastRefreshed ? `Updated ${lastRefreshed}` : "Live"}</span>
            </span>
            <button
              onClick={loadData}
              disabled={refreshing}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-canvas-card border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-700 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>
          </div>
        }
      />

      {/* Mandatory Safety Interlock Banner */}
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 shrink-0">
            <ShieldAlert size={18} />
          </div>
          <div>
            <div className="font-semibold text-amber-400 flex items-center space-x-2">
              <span>Safety Interlock Active: Workload Execution Locked</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 border border-amber-500/30 font-mono">
                WORKLOAD_EXECUTION: DISABLED
              </span>
            </div>
            <p className="text-text-muted mt-0.5 leading-relaxed">
              Stage 8/9 empirical evaluation has been successfully completed and verified. All 6 canonical workload profiles are permanently archived as immutable research artifacts. Workload injection is locked to preserve cluster stability.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0 font-mono text-[11px]">
          <span className="px-2 py-1 rounded bg-canvas-dark border border-canvas-border text-rose-400">
            Loadgenerator: 0 Replicas
          </span>
          <span className="px-2 py-1 rounded bg-canvas-dark border border-canvas-border text-amber-400">
            Actuator: DRY_RUN
          </span>
        </div>
      </div>

      {/* 1. Section: Experiment Overview KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard
          title="Workload Profiles"
          value={profiles.length || 6}
          unit="profiles"
          variant="cyan"
          icon={Layers}
          subtext="Independently configurable"
        />
        <MetricCard
          title="Completed Evaluations"
          value={HISTORICAL_EXPERIMENTS.length}
          unit="experiments"
          variant="emerald"
          icon={CheckCircle2}
          subtext="Verified Stage 8 dataset"
        />
        <MetricCard
          title="Active Workloads"
          value="0"
          unit="running"
          variant="purple"
          icon={Activity}
          subtext="Locked by safety interlock"
        />
        <MetricCard
          title="Evaluation Failures"
          value="0"
          unit="errors"
          variant="emerald"
          icon={ShieldCheck}
          subtext="100% execution completion"
        />
        <MetricCard
          title="Actuator Safety Mode"
          value="DRY_RUN"
          variant="amber"
          icon={Lock}
          subtext="Zero cluster mutations"
        />
      </div>

      {/* 2. Section: Six Workload Profiles Grid */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <SectionHeader
            title="Six Canonical Workload Profiles"
            subtitle="Configured synthetic load generation profiles representing diverse real-world e-commerce traffic dynamics"
            icon={Sliders}
          />
          {selectedProfile && (
            <span className="text-xs font-mono text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
              Selected: {selectedProfile.display_name}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(profiles.length > 0 ? profiles : HISTORICAL_EXPERIMENTS.map((h) => ({
            profile_name: h.profile,
            display_name: h.displayName,
            description: h.notes,
            target_host: "frontend:80",
            users: h.users,
            spawn_rate: 5,
            total_duration_seconds: h.durationSeconds,
            stages: [
              { stage_index: 0, name: "Ramp-Up", target_users: h.users, duration_seconds: 20, spawn_rate: 5 },
              { stage_index: 1, name: "Sustained", target_users: h.users, duration_seconds: h.durationSeconds - 40, spawn_rate: 5 },
              { stage_index: 2, name: "Ramp-Down", target_users: 0, duration_seconds: 20, spawn_rate: 5 },
            ],
            expected_observations: ["DPBPS bottleneck detection active", "Replica demand calculated"],
            custom_parameters: {},
            ramp_up_seconds: 20,
            steady_state_seconds: h.durationSeconds - 40,
            ramp_down_seconds: 20,
          }))).map((p) => {
            const isSelected = selectedProfile?.profile_name === p.profile_name;
            const matchedHist = HISTORICAL_EXPERIMENTS.find((h) => h.profile === p.profile_name);

            return (
              <div
                key={p.profile_name}
                onClick={() => {
                  setSelectedProfile(p);
                  if (matchedHist) setSelectedExperiment(matchedHist);
                }}
                className={`cursor-pointer rounded-xl p-4 transition-all duration-150 border flex flex-col justify-between ${
                  isSelected
                    ? "bg-cyan-950/20 border-cyan-500 shadow-md shadow-cyan-500/10 ring-1 ring-cyan-500/50"
                    : "bg-canvas-card border-canvas-border hover:border-slate-700 hover:bg-canvas-card/80"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <div className="p-1.5 rounded-lg bg-canvas-dark border border-canvas-border">
                        {getProfileIcon(p.profile_name)}
                      </div>
                      <h4 className="font-bold text-xs text-text-primary line-clamp-1">
                        {p.display_name}
                      </h4>
                    </div>
                    {isSelected && (
                      <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                        INSPECTING
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-text-secondary leading-relaxed mb-3 line-clamp-2">
                    {p.description}
                  </p>

                  <div className="grid grid-cols-3 gap-2 py-2 border-t border-canvas-border font-mono text-center text-xs">
                    <div className="p-1.5 rounded bg-canvas-dark border border-canvas-border">
                      <div className="text-[10px] text-text-muted">USERS</div>
                      <div className="font-bold text-text-primary mt-0.5">{p.users}</div>
                    </div>
                    <div className="p-1.5 rounded bg-canvas-dark border border-canvas-border">
                      <div className="text-[10px] text-text-muted">SPAWN</div>
                      <div className="font-bold text-text-primary mt-0.5">{p.spawn_rate}/s</div>
                    </div>
                    <div className="p-1.5 rounded bg-canvas-dark border border-canvas-border">
                      <div className="text-[10px] text-text-muted">DURATION</div>
                      <div className="font-bold text-text-primary mt-0.5">{p.total_duration_seconds}s</div>
                    </div>
                  </div>
                </div>

                <div className="mt-3 pt-2 border-t border-canvas-border flex items-center justify-between text-[11px] font-mono text-text-muted">
                  <span>Stages: {p.stages?.length || 3}</span>
                  <span className="text-cyan-400 hover:text-cyan-300 font-semibold flex items-center space-x-0.5">
                    <span>Inspect Details</span>
                    <ChevronRight size={12} />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Section: Selected Profile Inspector & Safety Validation */}
      {selectedProfile && (
        <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-canvas-border gap-2">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                {getProfileIcon(selectedProfile.profile_name)}
              </div>
              <div>
                <h3 className="text-base font-bold text-text-primary flex items-center space-x-2">
                  <span>{selectedProfile.display_name}</span>
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-canvas-dark text-text-muted border border-canvas-border">
                    {selectedProfile.profile_name}
                  </span>
                </h3>
                <p className="text-xs text-text-secondary mt-0.5">{selectedProfile.description}</p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={handleValidateConfig}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-canvas-dark border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-700 transition-colors"
              >
                <FileCheck size={13} />
                <span>Validate Safety Envelope</span>
              </button>
            </div>
          </div>

          {/* Validation Banner if clicked */}
          {validationResult && (
            <div
              className={`p-3 rounded-lg border text-xs flex items-start space-x-2 ${
                validationResult.valid
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                  : "bg-rose-500/10 border-rose-500/30 text-rose-300"
              }`}
            >
              {validationResult.valid ? (
                <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle size={16} className="text-rose-400 shrink-0 mt-0.5" />
              )}
              <div>
                <span className="font-bold">
                  {validationResult.valid
                    ? "Configuration Validated Successfully!"
                    : "Safety Constraints Violated:"}
                </span>
                <p className="mt-0.5 text-text-secondary font-sans">
                  {validationResult.valid
                    ? `Concurrency (${selectedProfile.users} users), spawn rate (${selectedProfile.spawn_rate}/s), and duration (${selectedProfile.total_duration_seconds}s) are within safe cluster load boundaries.`
                    : validationResult.errors.join(", ")}
                </p>
              </div>
            </div>
          )}

          {/* Profile Stage Breakdown Table */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider font-mono">
              Workload Stage Breakdown ({selectedProfile.stages?.length || 0} Stages)
            </h4>
            <div className="rounded-lg border border-canvas-border overflow-hidden">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                    <th className="py-2.5 px-3">Stage #</th>
                    <th className="py-2.5 px-3">Stage Name</th>
                    <th className="py-2.5 px-3 text-right">Target Users</th>
                    <th className="py-2.5 px-3 text-right">Duration (s)</th>
                    <th className="py-2.5 px-3 text-right">Spawn Rate (/s)</th>
                    <th className="py-2.5 px-4">Stage Objective</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-canvas-border">
                  {selectedProfile.stages?.map((stg) => (
                    <tr key={stg.stage_index} className="hover:bg-canvas-dark/30">
                      <td className="py-2.5 px-3 font-mono text-cyan-400 font-bold">
                        #{stg.stage_index + 1}
                      </td>
                      <td className="py-2.5 px-3 font-medium text-text-primary">{stg.name}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-primary font-bold">
                        {stg.target_users}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-secondary">
                        {stg.duration_seconds}s
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-secondary">
                        {stg.spawn_rate}
                      </td>
                      <td className="py-2.5 px-4 text-text-secondary">{stg.description || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Expected Observations */}
          <div className="p-3.5 rounded-lg bg-canvas-dark/60 border border-canvas-border space-y-1.5">
            <div className="text-[11px] font-mono font-bold text-text-secondary uppercase tracking-wider flex items-center space-x-1.5">
              <Sparkles size={13} className="text-cyan-400" />
              <span>Expected Algorithmic Scaling Responses:</span>
            </div>
            <ul className="space-y-1 text-xs text-text-secondary font-sans list-disc list-inside">
              {selectedProfile.expected_observations?.map((obs, i) => (
                <li key={i}>{obs}</li>
              ))}
            </ul>
          </div>

          {/* Action strip: Prepare Record & Locked Execute */}
          <div className="pt-3 border-t border-canvas-border flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex-1">
              <input
                type="text"
                placeholder="Optional experiment notes or hypothesis (e.g., 'Verifying bottleneck detection under stepped load')"
                value={experimentNotes}
                onChange={(e) => setExperimentNotes(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-lg bg-canvas-dark border border-canvas-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="flex items-center space-x-2 shrink-0">
              <button
                onClick={handlePrepareExperiment}
                disabled={creating}
                className="flex items-center space-x-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 transition-colors disabled:opacity-50"
              >
                <PlusCircle size={14} />
                <span>{creating ? "Preparing..." : "Prepare Record"}</span>
              </button>
              <button
                disabled
                title="Workload execution is strictly locked by safety interlock."
                className="flex items-center space-x-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-canvas-dark border border-canvas-border text-text-muted cursor-not-allowed opacity-60"
              >
                <XCircle size={14} />
                <span>Execute Workload (Locked)</span>
              </button>
            </div>
          </div>

          {creationSuccess && (
            <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-xs text-cyan-300 flex items-center space-x-2">
              <CheckCircle2 size={14} className="text-cyan-400 shrink-0" />
              <span>{creationSuccess}</span>
            </div>
          )}
        </div>
      )}

      {/* 4. Section: Experiment History & Telemetry Registry Table */}
      <div className="space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <SectionHeader
            title="Experiment History & Telemetry Registry"
            subtitle="Searchable registry of all verified Stage 8 execution runs and prepared experiment metadata"
            icon={Database}
          />

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleSelectAllCompare}
              className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-mono bg-canvas-dark border border-canvas-border text-text-secondary hover:text-text-primary hover:border-slate-700"
            >
              {comparedExpIds.length === HISTORICAL_EXPERIMENTS.length ? (
                <CheckSquare size={13} className="text-cyan-400" />
              ) : (
                <Square size={13} className="text-text-muted" />
              )}
              <span>Compare All ({comparedExpIds.length})</span>
            </button>

            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Search experiments..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 rounded-lg text-xs bg-canvas-dark border border-canvas-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-cyan-500 w-44 sm:w-52"
              />
            </div>

            <select
              value={profileFilter}
              onChange={(e) => setProfileFilter(e.target.value)}
              className="px-2 py-1.5 rounded-lg text-xs font-mono bg-canvas-dark border border-canvas-border text-text-primary focus:outline-none focus:border-cyan-500"
            >
              <option value="ALL">All Profiles</option>
              <option value="NORMAL_TRAFFIC">Normal Traffic</option>
              <option value="GRADUAL_TRAFFIC_INCREASE">Gradual Increase</option>
              <option value="SUDDEN_TRAFFIC_SPIKE">Sudden Spike</option>
              <option value="SUSTAINED_HIGH_TRAFFIC">Sustained High</option>
              <option value="TRAFFIC_DECREASE">Traffic Decrease</option>
              <option value="BURSTY_TRAFFIC">Bursty Traffic</option>
            </select>

            <div className="flex items-center space-x-1 bg-canvas-dark p-0.5 rounded-lg border border-canvas-border text-xs">
              {(["ALL", "COMPLETED", "CREATED"] as const).map((filter) => (
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
                  <th className="py-3 px-3 w-8 text-center">Compare</th>
                  <th className="py-3 px-3 font-semibold">Experiment ID</th>
                  <th className="py-3 px-3 font-semibold">Workload Profile</th>
                  <th className="py-3 px-3 font-semibold text-center">Status</th>
                  <th className="py-3 px-3 font-semibold text-right">Users</th>
                  <th className="py-3 px-3 font-semibold text-right">Duration</th>
                  <th className="py-3 px-3 font-semibold text-right">Avg RPS</th>
                  <th className="py-3 px-3 font-semibold text-right">Peak RPS</th>
                  <th className="py-3 px-3 font-semibold text-right">Avg P95</th>
                  <th className="py-3 px-3 font-semibold text-right">Peak P95</th>
                  <th className="py-3 px-3 font-semibold text-center">Scale Up</th>
                  <th className="py-3 px-3 font-semibold text-center">Dataset</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-canvas-border">
                {filteredExperiments.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="py-8 text-center text-text-muted">
                      No experiment records match the search criteria.
                    </td>
                  </tr>
                ) : (
                  filteredExperiments.map((exp) => {
                    const isSelected = selectedExperiment?.id === exp.id;
                    const isCompared = comparedExpIds.includes(exp.id);

                    return (
                      <tr
                        key={exp.id}
                        onClick={() => {
                          const matched = HISTORICAL_EXPERIMENTS.find((h) => h.id === exp.id);
                          if (matched) setSelectedExperiment(matched);
                        }}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-cyan-950/20 border-l-2 border-l-cyan-400"
                            : "hover:bg-canvas-dark/30"
                        }`}
                      >
                        <td
                          className="py-3 px-3 text-center"
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleCompare(exp.id);
                          }}
                        >
                          <button className="text-text-muted hover:text-cyan-400 transition-colors">
                            {isCompared ? (
                              <CheckSquare size={14} className="text-cyan-400" />
                            ) : (
                              <Square size={14} />
                            )}
                          </button>
                        </td>
                        <td className="py-3 px-3 font-mono font-bold text-text-primary text-[11px]">
                          {exp.id}
                        </td>
                        <td className="py-3 px-3 text-text-secondary">
                          <div className="flex items-center space-x-1.5">
                            {getProfileIcon(exp.profile)}
                            <span>{exp.profile}</span>
                          </div>
                        </td>
                        <td className="py-3 px-3 text-center">
                          <StatusBadge
                            status={exp.status}
                            variant={exp.status === "COMPLETED" ? "emerald" : "amber"}
                            size="xs"
                          />
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-text-primary">
                          {exp.users}
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-text-secondary">
                          {exp.duration}s
                        </td>
                        <td className="py-3 px-3 text-right font-mono font-bold text-cyan-400">
                          {exp.avgRps !== null ? exp.avgRps.toFixed(2) : "N/A"}
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-text-primary">
                          {exp.peakRps !== null ? exp.peakRps.toFixed(2) : "N/A"}
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-text-primary">
                          {exp.avgP95 !== null ? `${exp.avgP95.toFixed(1)} ms` : "N/A"}
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-text-secondary">
                          {exp.maxP95 !== null ? `${exp.maxP95.toFixed(1)} ms` : "N/A"}
                        </td>
                        <td className="py-3 px-3 text-center font-mono">
                          {exp.scaleUp !== null ? (
                            <span className="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 font-bold">
                              {exp.scaleUp}
                            </span>
                          ) : (
                            <span className="text-text-muted">-</span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-center">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                              exp.isHistorical
                                ? "bg-purple-500/10 border border-purple-500/20 text-purple-300 font-bold"
                                : "bg-canvas-dark border border-canvas-border text-text-muted"
                            }`}
                          >
                            {exp.isHistorical ? "HISTORICAL" : "PREPARED"}
                          </span>
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

      {/* 5. Section: Selected Experiment Deep-Dive & Metrics */}
      {selectedExperiment && (
        <div className="space-y-4">
          <SectionHeader
            title={`Experiment Deep-Dive: ${selectedExperiment.displayName}`}
            subtitle="Authoritative historical telemetry, DPBPS controller decisions, and actuation audit for this completed run"
            icon={Sparkles}
          />

          <div className="rounded-xl border border-canvas-border bg-canvas-card p-5 shadow-card space-y-5">
            {/* Experiment Title Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-canvas-border gap-2">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-mono text-xs text-cyan-400 font-bold">
                    {selectedExperiment.id}
                  </span>
                  <StatusBadge status={selectedExperiment.status} variant="emerald" size="xs" />
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/20 border border-purple-500/30 text-purple-300 font-bold">
                    STAGE 8 VERIFIED HISTORICAL RUN
                  </span>
                </div>
                <p className="text-xs text-text-secondary mt-1">{selectedExperiment.notes}</p>
              </div>

              <div className="text-xs font-mono text-text-muted flex items-center space-x-2">
                <span>Duration: <strong className="text-text-primary">{selectedExperiment.durationSeconds}s</strong></span>
                <span className="text-slate-600">•</span>
                <span>Peak Users: <strong className="text-cyan-400">{selectedExperiment.users}</strong></span>
              </div>
            </div>

            {/* Metric KPI cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 font-mono text-xs">
              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">AVG THROUGHPUT</div>
                <div className="text-base font-bold text-cyan-400 mt-1">
                  {selectedExperiment.avgFrontendRps.toFixed(2)} req/s
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">
                  Peak: {selectedExperiment.peakFrontendRps.toFixed(2)}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">AVG P95 LATENCY</div>
                <div className="text-base font-bold text-text-primary mt-1">
                  {selectedExperiment.avgFrontendP95Ms.toFixed(1)} ms
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">
                  Max: {selectedExperiment.maxFrontendP95Ms.toFixed(1)} ms
                </div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">MAX ERROR RATE</div>
                <div className="text-base font-bold text-text-primary mt-1">
                  {(selectedExperiment.maxErrorRate * 100).toFixed(2)}%
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">
                  {selectedExperiment.maxErrorRate === 0 ? "Zero Drops" : "Transient"}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">SCALE-UP ACTIONS</div>
                <div className="text-base font-bold text-rose-400 mt-1">
                  {selectedExperiment.scaleUpCount}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Bottleneck prioritized</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">SCALE-DOWN ACTIONS</div>
                <div className="text-base font-bold text-amber-400 mt-1">
                  {selectedExperiment.scaleDownCount}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">Dampened / Suppressed</div>
              </div>

              <div className="p-3 rounded-lg bg-canvas-dark border border-canvas-border">
                <div className="text-text-muted text-[10px]">EQUILIBRIUM HOLDS</div>
                <div className="text-base font-bold text-emerald-400 mt-1">
                  {selectedExperiment.holdCount}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">
                  Bottlenecks: {selectedExperiment.bottlenecksDetected}
                </div>
              </div>
            </div>

            {/* Actuator Audit Status Strip */}
            <div className="p-3.5 rounded-lg bg-canvas-dark/80 border border-canvas-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="flex items-center space-x-2">
                <Lock size={14} className="text-amber-400" />
                <span className="text-text-secondary">
                  Actuator Execution Mode: <strong>{selectedExperiment.actuatorMode}</strong>. Pods mutated during test: <strong>0</strong>.
                </span>
              </div>
              <div className="font-mono text-[11px] text-text-muted flex items-center space-x-2">
                <span>Total Decisions: <strong className="text-text-primary">{selectedExperiment.totalDecisions}</strong></span>
                <span className="text-slate-600">•</span>
                <span>Evaluations: <strong className="text-text-primary">{selectedExperiment.totalEvaluations}</strong></span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 6. Section: Multi-Experiment Comparison Interface */}
      {comparisonData.length > 1 && (
        <div className="space-y-4">
          <SectionHeader
            title={`Multi-Experiment Policy Comparison (${comparisonData.length} Profiles Selected)`}
            subtitle="Side-by-side performance comparison across throughput, latency percentiles, and DPBPS scaling dynamics"
            icon={BarChart3}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Chart 1: Throughput Comparison */}
            <div className="rounded-xl border border-canvas-border bg-canvas-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider font-mono">
                  Throughput: Average vs Peak RPS
                </h4>
                <span className="text-[10px] font-mono text-cyan-400">Requests / sec</span>
              </div>
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={comparisonData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                    <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 10 }} angle={-15} textAnchor="end" />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111827",
                        borderColor: "#1f293d",
                        borderRadius: "0.5rem",
                        fontSize: "0.75rem",
                      }}
                    />
                    <Bar dataKey="avgRps" name="Avg RPS" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="peakRps" name="Peak RPS" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 2: P95 Latency Comparison */}
            <div className="rounded-xl border border-canvas-border bg-canvas-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-text-secondary uppercase tracking-wider font-mono">
                  Latency Profile: Average vs Peak P95
                </h4>
                <span className="text-[10px] font-mono text-rose-400">Milliseconds (ms)</span>
              </div>
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={comparisonData} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" />
                    <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 10 }} angle={-15} textAnchor="end" />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111827",
                        borderColor: "#1f293d",
                        borderRadius: "0.5rem",
                        fontSize: "0.75rem",
                      }}
                    />
                    <Bar dataKey="avgP95" name="Avg P95 (ms)" fill="#a855f7" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="maxP95" name="Peak P95 (ms)" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Comparison Summary Table */}
          <div className="rounded-xl border border-canvas-border bg-canvas-card shadow-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-canvas-border bg-canvas-dark/60 text-text-muted font-mono text-[11px]">
                    <th className="py-3 px-4 font-semibold">Profile Name</th>
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
                  {comparisonData.map((row) => (
                    <tr key={row.id} className="hover:bg-canvas-dark/30">
                      <td className="py-3 px-4 font-bold text-text-primary">
                        {row.profile}
                      </td>
                      <td className="py-3 px-3 text-right text-text-secondary">{row.users}</td>
                      <td className="py-3 px-3 text-right text-text-secondary">{row.duration}s</td>
                      <td className="py-3 px-3 text-right font-bold text-cyan-400">{row.avgRps.toFixed(2)}</td>
                      <td className="py-3 px-3 text-right text-text-primary">{row.peakRps.toFixed(2)}</td>
                      <td className="py-3 px-3 text-right text-text-primary">{row.avgP95.toFixed(1)} ms</td>
                      <td className="py-3 px-3 text-right text-rose-400">{row.maxP95.toFixed(1)} ms</td>
                      <td className="py-3 px-3 text-right text-text-secondary">{row.errorRate}%</td>
                      <td className="py-3 px-3 text-center text-rose-400 font-bold">{row.scaleUp}</td>
                      <td className="py-3 px-3 text-center text-emerald-400">{row.hold}</td>
                      <td className="py-3 px-3 text-center text-amber-400">{row.bottlenecks}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
