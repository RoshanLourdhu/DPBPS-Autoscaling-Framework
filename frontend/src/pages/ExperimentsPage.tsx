// src/pages/ExperimentsPage.tsx
import { useEffect, useState, useCallback } from "react";
import {
  fetchWorkloadProfiles,
  fetchExperiments,
  validateExperimentConfig,
  createExperiment,
  updateExperimentStatus,
  stopExperiment,
} from "../services/api";
import type {
  WorkloadProfileConfig,
  ExperimentMetadata,
  ExperimentValidationResponse,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
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
} from "lucide-react";

export default function ExperimentsPage() {
  const [profiles, setProfiles] = useState<WorkloadProfileConfig[]>([]);
  const [experiments, setExperiments] = useState<ExperimentMetadata[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<WorkloadProfileConfig | null>(null);
  const [validationResult, setValidationResult] = useState<ExperimentValidationResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");
  const [experimentNotes, setExperimentNotes] = useState<string>("");
  const [creating, setCreating] = useState<boolean>(false);
  const [creationSuccess, setCreationSuccess] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setRefreshing(true);
    try {
      const [profs, exps] = await Promise.all([
        fetchWorkloadProfiles(),
        fetchExperiments(50),
      ]);
      setProfiles(profs);
      setExperiments(exps);
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

  const handleSelectProfile = (p: WorkloadProfileConfig) => {
    setSelectedProfile(p);
    setValidationResult(null);
    setCreationSuccess(null);
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
        tags: ["stage-7-prepared", selectedProfile.profile_name.toLowerCase()],
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

  const handleStatusToggle = async (expId: string, currentStatus: string) => {
    const nextStatus = currentStatus === "CREATED" ? "READY" : "CREATED";
    try {
      await updateExperimentStatus(expId, nextStatus);
      await loadData();
    } catch (e: any) {
      setError(`Status update rejected: ${e.message}`);
    }
  };

  const handleEmergencyStop = async (expId: string) => {
    try {
      await stopExperiment(expId, "Operator triggered emergency stop from UI");
      await loadData();
    } catch (e: any) {
      setError(`Emergency stop failed: ${e.message}`);
    }
  };

  if (loading) return <LoadingState />;
  if (error && profiles.length === 0) return <ErrorState message={error} />;

  const getProfileIcon = (name: string) => {
    switch (name) {
      case "NORMAL_TRAFFIC":
        return <Activity className="h-5 w-5 text-blue-600" />;
      case "GRADUAL_TRAFFIC_INCREASE":
        return <TrendingUp className="h-5 w-5 text-emerald-600" />;
      case "SUDDEN_TRAFFIC_SPIKE":
        return <Zap className="h-5 w-5 text-amber-600" />;
      case "SUSTAINED_HIGH_TRAFFIC":
        return <Flame className="h-5 w-5 text-red-600" />;
      case "TRAFFIC_DECREASE":
        return <TrendingDown className="h-5 w-5 text-purple-600" />;
      case "BURSTY_TRAFFIC":
        return <BarChart3 className="h-5 w-5 text-indigo-600" />;
      default:
        return <Sliders className="h-5 w-5 text-gray-600" />;
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* SECTION: MANDATORY SAFETY GUARDRAIL BANNERS */}
      <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <ShieldAlert className="h-6 w-6 text-amber-600 flex-shrink-0" />
          <div>
            <h3 className="text-sm font-bold text-amber-900 tracking-wide uppercase">
              Stage 8 Safety Lock Active: Workload Execution Disabled
            </h3>
            <p className="text-xs text-amber-700">
              Workload generation is locked (<code className="font-mono bg-amber-100 px-1 rounded">WORKLOAD_EXECUTION: DISABLED</code>),
              autoscaling is locked (<code className="font-mono bg-amber-100 px-1 rounded">SCALING_ENABLED=false</code>),
              and the Kubernetes actuator operates strictly in <code className="font-mono bg-amber-100 px-1 rounded">DRY-RUN</code> mode.
              No synthetic traffic is launched and zero cluster mutations occur during this audit.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-bold bg-red-100 text-red-800 border border-red-200">
            WORKLOAD: DISABLED
          </span>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-bold bg-amber-100 text-amber-800 border border-amber-200">
            AUTOSCALING: DISABLED
          </span>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-bold bg-blue-100 text-blue-800 border border-blue-200">
            ACTUATOR: DRY-RUN
          </span>
        </div>
      </div>

      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <PageHeader
          title="DPBPS Workload Generation & Experiment Management"
          subtitle="Stage 7: Reproducible Workload Profiles, Safety Validation, and Telemetry Recording Framework"
        />
        <div className="flex items-center space-x-3">
          <div className="text-xs text-gray-500 flex items-center space-x-1">
            <Clock className="h-3.5 w-3.5" />
            <span>Updated: {lastRefreshed || "Just now"}</span>
          </div>
          <button
            onClick={loadData}
            disabled={refreshing}
            className="flex items-center space-x-1 px-3 py-1.5 text-xs font-medium rounded bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin text-blue-600" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Available Profiles</div>
          <div className="text-2xl font-bold text-gray-900 mt-1">{profiles.length}</div>
          <div className="text-[11px] text-gray-500 mt-0.5">Independently selectable</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Prepared Experiments</div>
          <div className="text-2xl font-bold text-indigo-600 mt-1">{experiments.length}</div>
          <div className="text-[11px] text-gray-500 mt-0.5">Stored in results/experiments</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Target Application</div>
          <div className="text-lg font-bold text-gray-900 mt-1 font-mono">frontend:80</div>
          <div className="text-[11px] text-gray-500 mt-0.5">Online Boutique Frontend Entry</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Execution Posture</div>
          <div className="text-lg font-bold text-amber-600 mt-1 flex items-center space-x-1">
            <ShieldCheck className="h-4 w-4" />
            <span>PREPARATION ONLY</span>
          </div>
          <div className="text-[11px] text-amber-700 mt-0.5">Workload launcher locked</div>
        </div>
      </div>

      {/* SECTION: SIX WORKLOAD PROFILES GRID */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center space-x-2">
              <Layers className="h-4 w-4 text-blue-600" />
              <span>Six Configurable Workload Profiles</span>
            </h2>
            <p className="text-xs text-gray-500">
              Select a profile to inspect its multi-stage traffic parameters, expected DPBPS responses, and safety boundaries.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {profiles.map((p) => {
            const isSelected = selectedProfile?.profile_name === p.profile_name;
            return (
              <div
                key={p.profile_name}
                onClick={() => handleSelectProfile(p)}
                className={`cursor-pointer rounded-lg border p-4 transition-all flex flex-col justify-between ${isSelected
                    ? "bg-blue-50/40 border-blue-500 shadow-sm ring-1 ring-blue-500"
                    : "bg-white border-gray-200 hover:border-gray-300 hover:shadow-xs"
                  }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      {getProfileIcon(p.profile_name)}
                      <span className="font-bold text-xs text-gray-900">{p.display_name}</span>
                    </div>
                    {isSelected && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-800">
                        Selected
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-600 mt-2 line-clamp-2">{p.description}</p>

                  <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-gray-100 text-center">
                    <div className="bg-gray-50 p-2 rounded">
                      <div className="text-[10px] text-gray-500 uppercase">Users</div>
                      <div className="text-xs font-bold text-gray-800 font-mono">{p.users}</div>
                    </div>
                    <div className="bg-gray-50 p-2 rounded">
                      <div className="text-[10px] text-gray-500 uppercase">Spawn Rate</div>
                      <div className="text-xs font-bold text-gray-800 font-mono">{p.spawn_rate}/s</div>
                    </div>
                    <div className="bg-gray-50 p-2 rounded">
                      <div className="text-[10px] text-gray-500 uppercase">Duration</div>
                      <div className="text-xs font-bold text-gray-800 font-mono">{p.total_duration_seconds}s</div>
                    </div>
                  </div>
                </div>

                <div className="mt-3 pt-2 border-t border-gray-100 text-[11px] text-gray-500 flex items-center justify-between">
                  <span>Stages: {p.stages.length}</span>
                  <span className="font-semibold text-blue-600">Inspect Details &rarr;</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION: SELECTED PROFILE INSPECTOR & EXPERIMENT PREPARATION */}
      {selectedProfile && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 pb-3 border-b border-gray-200">
            <div>
              <div className="flex items-center space-x-2">
                {getProfileIcon(selectedProfile.profile_name)}
                <h3 className="text-base font-bold text-gray-900">{selectedProfile.display_name}</h3>
                <span className="font-mono text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-700">
                  {selectedProfile.profile_name}
                </span>
              </div>
              <p className="text-xs text-gray-600 mt-1">{selectedProfile.description}</p>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={handleValidateConfig}
                className="flex items-center space-x-1 px-3 py-1.5 text-xs font-semibold rounded bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
              >
                <FileCheck className="h-3.5 w-3.5" />
                <span>Validate Safety</span>
              </button>
            </div>
          </div>

          {/* Validation Banner if validated */}
          {validationResult && (
            <div
              className={`p-3 rounded-lg border text-xs flex items-start space-x-2 ${validationResult.valid
                  ? "bg-green-50 border-green-200 text-green-800"
                  : "bg-red-50 border-red-200 text-red-800"
                }`}
            >
              {validationResult.valid ? (
                <CheckCircle2 className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-red-600 flex-shrink-0 mt-0.5" />
              )}
              <div>
                <span className="font-bold">
                  {validationResult.valid
                    ? "Configuration Validated Successfully!"
                    : "Configuration Safety Violations Detected:"}
                </span>
                {validationResult.valid ? (
                  <p className="mt-0.5 text-green-700">
                    Concurrency ({selectedProfile.users} users), spawn rate ({selectedProfile.spawn_rate}/s),
                    and total duration ({selectedProfile.total_duration_seconds}s) are within safe operating limits.
                  </p>
                ) : (
                  <ul className="list-disc list-inside mt-1 space-y-0.5">
                    {validationResult.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          {/* Creation notification */}
          {creationSuccess && (
            <div className="p-3 rounded-lg bg-indigo-50 border border-indigo-200 text-xs text-indigo-900 flex items-center space-x-2">
              <CheckCircle2 className="h-4 w-4 text-indigo-600 flex-shrink-0" />
              <span>{creationSuccess}</span>
            </div>
          )}

          {/* Multi-Stage Configuration Breakdown Table */}
          <div>
            <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">
              Profile Stage Breakdown ({selectedProfile.stages.length} Stages)
            </h4>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 text-xs">
                <thead className="bg-gray-50 text-gray-600 font-semibold uppercase">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left">Stage</th>
                    <th scope="col" className="px-3 py-2 text-left">Name</th>
                    <th scope="col" className="px-3 py-2 text-right">Target Users</th>
                    <th scope="col" className="px-3 py-2 text-right">Duration (s)</th>
                    <th scope="col" className="px-3 py-2 text-right">Spawn Rate (/s)</th>
                    <th scope="col" className="px-4 py-2 text-left">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {selectedProfile.stages.map((stg) => (
                    <tr key={stg.stage_index} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono font-semibold text-gray-700">#{stg.stage_index + 1}</td>
                      <td className="px-3 py-2 font-medium text-gray-900">{stg.name}</td>
                      <td className="px-3 py-2 text-right font-mono font-bold text-gray-800">{stg.target_users}</td>
                      <td className="px-3 py-2 text-right font-mono text-gray-600">{stg.duration_seconds}s</td>
                      <td className="px-3 py-2 text-right font-mono text-gray-600">{stg.spawn_rate}</td>
                      <td className="px-4 py-2 text-gray-500">{stg.description || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Expected Observations */}
          <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
            <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5 flex items-center space-x-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-blue-600" />
              <span>Expected Metric & DPBPS Scaling Observations</span>
            </h4>
            <ul className="list-disc list-inside space-y-1 text-xs text-gray-600">
              {selectedProfile.expected_observations.map((obs, i) => (
                <li key={i}>{obs}</li>
              ))}
            </ul>
          </div>

          {/* Prepare Experiment Action Strip */}
          <div className="pt-3 border-t border-gray-200 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex-1">
              <input
                type="text"
                placeholder="Optional experiment notes or hypothesis (e.g. 'Evaluating leaf bottleneck detection under surge')"
                value={experimentNotes}
                onChange={(e) => setExperimentNotes(e.target.value)}
                className="w-full text-xs px-3 py-2 border border-gray-300 rounded shadow-xs focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={handlePrepareExperiment}
                disabled={creating}
                className="flex items-center space-x-1 px-4 py-2 text-xs font-bold rounded bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm transition-colors disabled:opacity-50"
              >
                <PlusCircle className="h-4 w-4" />
                <span>{creating ? "Preparing..." : "Prepare Experiment Record"}</span>
              </button>

              {/* Explicitly disabled execute button with tooltip */}
              <button
                disabled
                title="Workload execution is strictly disabled in Stage 8 audit and validation."
                className="flex items-center space-x-1 px-4 py-2 text-xs font-bold rounded bg-gray-200 text-gray-400 cursor-not-allowed border border-gray-300"
              >
                <XCircle className="h-4 w-4" />
                <span>Execute Workload (Locked)</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SECTION: EXPERIMENT HISTORY & METADATA TABLE */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
              Experiment Metadata & Preparation Registry
            </h3>
            <p className="text-xs text-gray-500">
              Persisted experiment records and metadata in <code className="font-mono">results/experiments</code>.
            </p>
          </div>
          <span className="text-xs font-medium text-gray-500">
            Total records: {experiments.length}
          </span>
        </div>

        {experiments.length === 0 ? (
          <div className="p-8 text-center text-xs text-gray-500">
            No experiments found in storage. Select a profile above and click &quot;Prepare Experiment Record&quot;.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-xs">
              <thead className="bg-gray-50 text-gray-600 font-semibold uppercase">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left">Experiment ID</th>
                  <th scope="col" className="px-3 py-3 text-left">Profile</th>
                  <th scope="col" className="px-3 py-3 text-center">Status</th>
                  <th scope="col" className="px-3 py-3 text-right">Users</th>
                  <th scope="col" className="px-3 py-3 text-right">Duration</th>
                  <th scope="col" className="px-3 py-3 text-left">Created At</th>
                  <th scope="col" className="px-4 py-3 text-left">Notes</th>
                  <th scope="col" className="px-3 py-3 text-center">Lifecycle Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {experiments.map((exp) => (
                  <tr key={exp.experiment_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono font-bold text-gray-800 text-[11px]">
                      {exp.experiment_id}
                    </td>
                    <td className="px-3 py-2.5 font-medium text-gray-900">
                      {exp.profile_name}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${exp.status === "READY"
                            ? "bg-green-100 text-green-800"
                            : exp.status === "CREATED"
                              ? "bg-blue-100 text-blue-800"
                              : exp.status === "COMPLETED"
                                ? "bg-gray-100 text-gray-700"
                                : exp.status === "RUNNING"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-red-100 text-red-800"
                          }`}
                      >
                        {exp.status}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-gray-700">
                      {exp.selected_concurrency}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-gray-700">
                      {exp.configuration?.total_duration_seconds ? `${exp.configuration.total_duration_seconds}s` : "-"}
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 text-[11px]">
                      {new Date(exp.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-gray-500 max-w-xs truncate text-[11px]">
                      {exp.notes || "-"}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <div className="flex items-center justify-center space-x-1.5">
                        {exp.status === "CREATED" || exp.status === "READY" ? (
                          <button
                            onClick={() => handleStatusToggle(exp.experiment_id, exp.status)}
                            className="px-2 py-1 text-[11px] font-medium rounded bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300 transition-colors"
                          >
                            Mark {exp.status === "CREATED" ? "READY" : "CREATED"}
                          </button>
                        ) : (
                          <span className="text-gray-400 text-[11px]">Locked</span>
                        )}
                        <button
                          onClick={() => handleEmergencyStop(exp.experiment_id)}
                          className="px-2 py-1 text-[11px] font-medium rounded bg-red-50 text-red-700 hover:bg-red-100 border border-red-200 transition-colors"
                          title="Trigger emergency stop (scales loadgenerator to 0)"
                        >
                          Stop
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
