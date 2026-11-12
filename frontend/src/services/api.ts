// src/services/api.ts
/** API service helpers for the DPBPS frontend */
export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/** Helper to build full URL */
function url(path: string): string {
  return `${API_BASE}${path}`;
}

/** Generic GET fetch wrapper */
async function request<T>(path: string): Promise<T> {
  const resp = await fetch(url(path));
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`API error ${resp.status}: ${err}`);
  }
  return (await resp.json()) as T;
}

/** Generic POST fetch wrapper */
async function postRequest<T>(path: string, body: any): Promise<T> {
  const resp = await fetch(url(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`API error ${resp.status}: ${err}`);
  }
  return (await resp.json()) as T;
}

// ---------------------------------------------------------------------
// HEALTH & ENVIRONMENT
// ---------------------------------------------------------------------
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  kubernetes_connected?: boolean;
  prometheus_connected?: boolean;
  dry_run?: boolean;
  scaling_enabled?: boolean;
  emergency_stop?: boolean;
  deployment_phase?: string;
}
export const fetchHealth = () => request<HealthResponse>("/api/v1/health");

export interface EnvironmentInfo {
  id: string;
  name: string;
  description?: string;
  status: string;
}
export const fetchEnvironments = () => request<EnvironmentInfo[]>("/api/v1/environments");

// ---------------------------------------------------------------------
// METRICS & SERVICES
// ---------------------------------------------------------------------
export interface Metric {
  name: string;
  value: number;
  unit: string;
  timestamp: string;
  environment_id: string;
  service_id?: string;
  source: string;
  simulated: boolean;
}

export interface OverviewMetricsResponse {
  metrics: Metric[];
}
export const fetchOverviewMetrics = () => request<OverviewMetricsResponse>("/api/v1/metrics/overview");

export interface ServiceInfo {
  id: string;
  name: string;
  environment_id: string;
  health: string;
  ready_replicas: number;
  desired_replicas?: number;
  cpu_utilisation: number;
  memory_utilisation: number;
  request_rate: number;
  p95_latency: number;
  error_rate: number;
  dependencies?: string[];
  telemetry_available?: boolean;
  missing_metrics?: string[];
  deployment_phase?: string;
}
export const fetchServices = () => request<ServiceInfo[]>("/api/v1/services");

// ---------------------------------------------------------------------
// SCALING & DEPLOYMENTS
// ---------------------------------------------------------------------
export interface ScalingConfig {
  strategy: string;
  min_replicas: number;
  max_replicas: number;
  cpu_threshold: number;
  memory_threshold: number;
  latency_target_ms: number;
  scale_up_window_sec: number;
  scale_down_window_sec: number;
  cooldown_sec: number;
}
export const fetchScalingConfig = () => request<ScalingConfig>("/api/v1/scaling/config");

export interface ScalingEvent {
  timestamp: string;
  environment_id: string;
  service_id: string;
  previous_replicas: number;
  requested_replicas: number;
  actual_replicas: number;
  decision: string;
  reason: string;
}
export const fetchScalingEvents = () => request<ScalingEvent[]>("/api/v1/scaling/events");

export interface DeploymentInfo {
  id: string;
  version: string;
  status: string;
  start_time: string;
  end_time?: string;
  ready_replicas: number;
  unavailable_replicas: number;
  phase: string;
}
export const fetchDeployments = () => request<DeploymentInfo[]>("/api/v1/deployments");

export interface ScalingStatusResponse {
  simulation_mode: boolean;
  dry_run: boolean;
  scaling_enabled: boolean;
  phase: string;
  config: ScalingConfig;
  latest_decision?: any;
  controller_running?: boolean;
  controller_paused?: boolean;
  interval_seconds?: number;
  cycle_count?: number;
  last_evaluation_time?: string;
  last_evaluation_duration_ms?: number;
  next_evaluation_time?: string;
  current_bottleneck?: string;
  total_decisions_recorded?: number;
}
export const fetchScalingStatus = () => request<ScalingStatusResponse>("/api/v1/scaling/status");

export interface ContinuousControllerStatus {
  is_running: boolean;
  is_paused: boolean;
  interval_seconds: number;
  cycle_count: number;
  last_evaluation_time?: string;
  last_evaluation_duration_ms?: number;
  next_evaluation_time?: string;
  current_bottleneck?: string;
  deployment_phase: string;
  scaling_enabled: boolean;
  dry_run: boolean;
  total_decisions_recorded: number;
  latest_cycle_summary?: any;
}

export const fetchControllerStatus = () =>
  request<ContinuousControllerStatus>("/api/v1/dpbps/controller/status");

export const startContinuousController = () =>
  postRequest<{ status: string; running: boolean; interval_seconds: number }>("/api/v1/dpbps/controller/start", {});

export const stopContinuousController = () =>
  postRequest<{ status: string; running: boolean }>("/api/v1/dpbps/controller/stop", {});

export const pauseContinuousController = () =>
  postRequest<{ status: string; paused: boolean }>("/api/v1/dpbps/controller/pause", {});

export const resumeContinuousController = () =>
  postRequest<{ status: string; paused: boolean }>("/api/v1/dpbps/controller/resume", {});

export const setControllerInterval = (interval_seconds: number) =>
  postRequest<{ interval_seconds: number }>("/api/v1/dpbps/controller/interval", { interval_seconds });

export const fetchControllerHistory = (limit: number = 20) =>
  request<any[]>(`/api/v1/dpbps/controller/history?limit=${limit}`);

export const fetchControllerDecisions = (service_name?: string, limit: number = 50) => {
  const url = service_name
    ? `/api/v1/dpbps/controller/decisions?service_name=${service_name}&limit=${limit}`
    : `/api/v1/dpbps/controller/decisions?limit=${limit}`;
  return request<any[]>(url);
};

export interface DecisionRecord {
  service_name: string;
  action: string;
  previous_replicas: number;
  requested_replicas: number;
  priority_score?: number;
  phase: string;
  bottleneck?: string;
  reason: string;
  timestamp: string;
  simulated: boolean;
}
export const fetchScalingDecisions = (limit: number = 20) =>
  request<DecisionRecord[]>(`/api/v1/scaling/decisions?limit=${limit}`);

// ---------------------------------------------------------------------
// DPBPS END-TO-END PIPELINE & KUBERNETES ACTUATOR
// ---------------------------------------------------------------------
export interface PipelineServiceResult {
  service_name: string;
  request_rate?: number;
  p95_latency?: number;
  error_rate?: number;
  cpu_utilization?: number;
  memory_utilization?: number;
  current_replicas: number;
  ready_replicas: number;
  deployment_phase: string;
  bottleneck_information?: string;
  dpbps_decision: string;
  proposed_replica_count: number;
  actuator_execution_status: string;
  reason: string;
  cluster_modified: boolean;
  telemetry_complete: boolean;
  missing_metrics: string[];
  dependencies: string[];
  timestamp: string;
}

export interface PipelineEvaluationResponse {
  timestamp: string;
  deployment_phase: string;
  execution_mode: string;
  cluster_modified: boolean;
  total_services: number;
  complete_telemetry_services: number;
  incomplete_telemetry_services: number;
  bottleneck_service?: string;
  scale_up_count: number;
  scale_down_count: number;
  hold_count: number;
  services: PipelineServiceResult[];
}
export const fetchPipelineEvaluation = () =>
  request<PipelineEvaluationResponse>("/api/v1/dpbps/pipeline/evaluate");

export const triggerPipelineEvaluation = () =>
  postRequest<PipelineEvaluationResponse>("/api/v1/dpbps/pipeline/evaluate", {});

export interface ActuatorResult {
  service_name: string;
  namespace: string;
  current_replicas: number;
  requested_replicas: number;
  action: string;
  execution_mode: string;
  status: string;
  cluster_modified: boolean;
  reason: string;
  deployment_phase: string;
  timestamp: string;
  details?: Record<string, any>;
}
export const fetchActuatorHistory = (limit: number = 20) =>
  request<ActuatorResult[]>(`/api/v1/scaling/actuator/history?limit=${limit}`);

export interface TelemetrySummary {
  namespace: string;
  deployment_count: number;
  complete_telemetry_count: number;
  incomplete_telemetry_count: number;
  application_metrics_integrated: boolean;
  deployment_phase: string;
  deployments: any[];
}
export const fetchTelemetrySummary = () =>
  request<TelemetrySummary>("/api/v1/kubernetes/telemetry/summary");

export type DeploymentPhase =
  | "NORMAL_OPERATION"
  | "PRE_DEPLOYMENT"
  | "ACTIVE_DEPLOYMENT"
  | "POST_DEPLOYMENT";

export interface DeploymentPhaseOption {
  id: DeploymentPhase;
  label: string;
  desc: string;
}

export const DEPLOYMENT_PHASES: DeploymentPhaseOption[] = [
  {
    id: "NORMAL_OPERATION",
    label: "Normal Operation",
    desc: "Standard DPBPS evaluation with baseline scaling thresholds",
  },
  {
    id: "PRE_DEPLOYMENT",
    label: "Pre-Deployment",
    desc: "Deployment preparation phase prior to rollout initiation",
  },
  {
    id: "ACTIVE_DEPLOYMENT",
    label: "Active Deployment",
    desc: "Suppresses scale-down decisions to protect rollout stability",
  },
  {
    id: "POST_DEPLOYMENT",
    label: "Post-Deployment",
    desc: "Enforces stabilization window before permitting scale-down",
  },
];

export const updateDeploymentPhase = (phase: DeploymentPhase | string, serviceName?: string) =>
  postRequest<{ phase: DeploymentPhase; service_name?: string }>("/api/v1/scaling/deployment-phase", {
    phase,
    service_name: serviceName || null,
  });

// ---------------------------------------------------------------------
// CI/CD WEBHOOK & ROLLOUT RECONCILIATION
// ---------------------------------------------------------------------
export interface CicdEvent {
  event_id: string;
  service_name: string;
  event_type: "started" | "progressing" | "succeeded" | "failed" | "cancelled" | string;
  timestamp: string;
  previous_phase: string;
  new_phase: string;
  commit_sha?: string;
  image_tag?: string;
  pipeline_id?: string;
  details?: Record<string, any>;
}

export interface CicdWebhookPayload {
  event_id: string;
  service_name: string;
  event_type: "started" | "progressing" | "succeeded" | "failed" | "cancelled" | string;
  timestamp?: string;
  commit_sha?: string;
  image_tag?: string;
  pipeline_id?: string;
  details?: Record<string, any>;
}

export interface RolloutCondition {
  type: string;
  status: string;
  reason?: string;
  message?: string;
}

export interface RolloutStatus {
  service_name: string;
  current_phase: string;
  generation: number;
  observed_generation: number;
  desired_replicas: number;
  updated_replicas: number;
  ready_replicas: number;
  available_replicas: number;
  unavailable_replicas: number;
  rollout_in_progress: boolean;
  conditions: RolloutCondition[];
  timestamp?: string;
}

export interface ReconciliationResult {
  service_name: string;
  previous_phase?: string;
  reconciled_phase?: string;
  action?: string;
  rollout_failed?: boolean;
  failure_reason?: string;
  generation?: number;
  observed_generation?: number;
  error?: string;
}

export const fetchCicdEvents = (serviceName?: string, limit: number = 50) => {
  const query = serviceName ? `?service_name=${encodeURIComponent(serviceName)}&limit=${limit}` : `?limit=${limit}`;
  return request<CicdEvent[]>(`/api/v1/cicd/events${query}`);
};

export const sendCicdWebhookEvent = (payload: CicdWebhookPayload) =>
  postRequest<{ status: string; message: string; event: CicdEvent }>("/api/v1/cicd/events", payload);

export const fetchRolloutStatus = () =>
  request<RolloutStatus[]>("/api/v1/deployments/rollout/status");

export const reconcileDeployments = (serviceName?: string) =>
  postRequest<ReconciliationResult[]>("/api/v1/deployments/reconcile", { service_name: serviceName || null });

// ---------------------------------------------------------------------
// ACTUATOR STATUS & EMERGENCY STOP CONTROLS
// ---------------------------------------------------------------------
export interface ActuatorStatusResponse {
  namespace: string;
  dry_run: boolean;
  global_scaling_enabled: boolean;
  emergency_stop: boolean;
  emergency_stop_reason?: string | null;
  emergency_stop_timestamp?: string | null;
  approved_services: string[];
  protected_infrastructure: string[];
  allowlist: string[];
  limits: {
    min_replicas: number;
    max_replicas: number;
    max_replica_change: number;
    cooldown_sec: number;
    scale_down_stabilization_sec: number;
  };
  reliability: {
    max_retries: number;
    readiness_timeout_sec: number;
    telemetry_freshness_threshold_sec: number;
  };
}

export const fetchActuatorStatus = () =>
  request<ActuatorStatusResponse>("/api/v1/scaling/actuator/status");

export const toggleEmergencyStop = (enabled: boolean, reason?: string) =>
  postRequest<{ emergency_stop: boolean; reason?: string }>("/api/v1/scaling/actuator/emergency-stop", {
    enabled,
    reason: reason || "Operator manual toggle via Scaling Dashboard",
  });

export const triggerActuatorRollback = (serviceName: string, rollbackReplicas: number, reason?: string) =>
  postRequest<{
    service_name: string;
    rollback_status: string;
    reverted_to: number;
    reason: string;
    cluster_modified: boolean;
  }>("/api/v1/scaling/actuator/rollback", {
    service_name: serviceName,
    rollback_replicas: rollbackReplicas,
    reason: reason || "Manual rollback requested via dashboard",
  });

// ---------------------------------------------------------------------
// EXPERIMENTS & WORKLOAD PROFILES
// ---------------------------------------------------------------------
export interface WorkloadStage {
  stage_index: number;
  name: string;
  target_users: number;
  duration_seconds: number;
  spawn_rate: number;
  description?: string;
}

export interface WorkloadProfileConfig {
  profile_name: string;
  display_name: string;
  description: string;
  target_host: string;
  users: number;
  spawn_rate: number;
  ramp_up_seconds: number;
  steady_state_seconds: number;
  ramp_down_seconds: number;
  total_duration_seconds: number;
  stages: WorkloadStage[];
  expected_observations: string[];
  custom_parameters: Record<string, any>;
}

export interface ExperimentMetadata {
  experiment_id: string;
  profile_name: string;
  configuration: WorkloadProfileConfig;
  application_entry_point: string;
  created_at: string;
  start_timestamp?: string;
  end_timestamp?: string;
  status: string;
  selected_concurrency: number;
  target_request_rate?: number;
  actual_observed_request_rate?: number;
  failure_information?: string;
  execution_disabled: boolean;
  tags: string[];
  notes?: string;
}

export interface ExperimentValidationResponse {
  valid: boolean;
  errors: string[];
  profile_name: string;
  safety_checks_passed: boolean;
  configuration?: WorkloadProfileConfig;
}

export interface ExperimentMetricsCollection {
  experiment_id: string;
  profile_name: string;
  start_timestamp?: string;
  end_timestamp?: string;
  total_snapshots: number;
  snapshots: any[];
}

export const fetchWorkloadProfiles = () =>
  request<WorkloadProfileConfig[]>("/api/v1/experiments/profiles");

export const fetchWorkloadProfile = (name: string) =>
  request<WorkloadProfileConfig>(`/api/v1/experiments/profiles/${name}`);

export const validateExperimentConfig = (config: WorkloadProfileConfig) =>
  postRequest<ExperimentValidationResponse>("/api/v1/experiments/validate", config);

export const createExperiment = (payload: {
  profile_name: string;
  custom_configuration?: WorkloadProfileConfig;
  notes?: string;
  tags?: string[];
}) => postRequest<ExperimentMetadata>("/api/v1/experiments", payload);

export const fetchExperiments = (limit: number = 50) =>
  request<ExperimentMetadata[]>(`/api/v1/experiments?limit=${limit}`);

export const fetchExperiment = (experimentId: string) =>
  request<ExperimentMetadata>(`/api/v1/experiments/${experimentId}`);

export const fetchExperimentMetrics = (experimentId: string) =>
  request<ExperimentMetricsCollection>(`/api/v1/experiments/${experimentId}/metrics`);

export const updateExperimentStatus = (
  experimentId: string,
  status: string,
  failureInformation?: string
) =>
  postRequest<ExperimentMetadata>(`/api/v1/experiments/${experimentId}/status`, {
    status,
    failure_information: failureInformation,
  });

export interface ExperimentSafetyCheck {
  experiment_id: string;
  can_execute: boolean;
  blocking_reasons: string[];
  master_execution_enabled: boolean;
  scaling_enabled: boolean;
  actuator_mode: string;
}

export const checkExperimentSafety = (experimentId: string) =>
  request<ExperimentSafetyCheck>(`/api/v1/experiments/${experimentId}/safety-check`);

export const stopExperiment = (experimentId: string, reason: string = "Operator stop requested") =>
  postRequest<any>(`/api/v1/experiments/${experimentId}/stop?reason=${encodeURIComponent(reason)}`, {});

// ---------------------------------------------------------------------
// VERIFIED HISTORICAL EXPERIMENT EVALUATION RECORDS (STAGE 8/9 DATASET)
// ---------------------------------------------------------------------
export interface HistoricalExperimentSummary {
  id: string;
  profile: string;
  displayName: string;
  status: string;
  createdAt: string;
  startedAt: string;
  endedAt: string;
  durationSeconds: number;
  targetDurationSeconds: number;
  avgFrontendRps: number;
  peakFrontendRps: number;
  avgFrontendP95Ms: number;
  maxFrontendP95Ms: number;
  maxErrorRate: number;
  scaleUpCount: number;
  scaleDownCount: number;
  holdCount: number;
  bottlenecksDetected: number;
  clusterModified: boolean;
  actuatorMode: string;
  users: number;
  notes: string;
  tags: string[];
  totalDecisions: number;
  totalEvaluations: number;
}

export const HISTORICAL_EXPERIMENTS: HistoricalExperimentSummary[] = [
  {
    id: "exp_20261110T152425_normal_traffic_838109a5",
    profile: "NORMAL_TRAFFIC",
    displayName: "Profile 1: Normal Traffic Baseline",
    status: "COMPLETED",
    createdAt: "2026-11-10T15:24:25.856401+00:00",
    startedAt: "2026-11-10T15:24:25.856401+00:00",
    endedAt: "2026-11-10T15:26:45.856401+00:00",
    durationSeconds: 140,
    targetDurationSeconds: 130,
    avgFrontendRps: 5.78,
    peakFrontendRps: 10.31,
    avgFrontendP95Ms: 255.91,
    maxFrontendP95Ms: 1360.97,
    maxErrorRate: 0.0,
    scaleUpCount: 1,
    scaleDownCount: 0,
    holdCount: 107,
    bottlenecksDetected: 0,
    clusterModified: false,
    actuatorMode: "DRY_RUN",
    users: 10,
    notes: "Live Stage 8.5 E01 normal traffic baseline validation run",
    tags: ["stage-8.5", "e01", "normal-traffic", "live-run"],
    totalDecisions: 108,
    totalEvaluations: 14,
  },
  {
    id: "exp_20261110T165351_gradual_traffic_increase_309b2d79",
    profile: "GRADUAL_TRAFFIC_INCREASE",
    displayName: "Profile 2: Gradual Traffic Increase",
    status: "COMPLETED",
    createdAt: "2026-11-10T16:53:51.148661+00:00",
    startedAt: "2026-11-10T16:53:51.162564+00:00",
    endedAt: "2026-11-10T16:57:01.526419+00:00",
    durationSeconds: 190.1,
    targetDurationSeconds: 180,
    avgFrontendRps: 18.63,
    peakFrontendRps: 51.46,
    avgFrontendP95Ms: 1112.7,
    maxFrontendP95Ms: 4171.87,
    maxErrorRate: 0.0,
    scaleUpCount: 7,
    scaleDownCount: 0,
    holdCount: 171,
    bottlenecksDetected: 80,
    clusterModified: false,
    actuatorMode: "DRY_RUN",
    users: 50,
    notes: "Live Stage 8.5 E02 gradual traffic increase (10 -> 25 -> 50 users @ 2 u/s, 180s)",
    tags: ["stage-8.5", "e02", "gradual-traffic", "live-run"],
    totalDecisions: 178,
    totalEvaluations: 19,
  },
  {
    id: "exp_20261110T170244_sudden_traffic_spike_d80c4694",
    profile: "SUDDEN_TRAFFIC_SPIKE",
    displayName: "Profile 3: Sudden Traffic Spike",
    status: "COMPLETED",
    createdAt: "2026-11-10T17:02:44.550907+00:00",
    startedAt: "2026-11-10T17:02:44.564099+00:00",
    endedAt: "2026-11-10T17:04:54.903661+00:00",
    durationSeconds: 130,
    targetDurationSeconds: 120,
    avgFrontendRps: 35.7,
    peakFrontendRps: 83.57,
    avgFrontendP95Ms: 808.61,
    maxFrontendP95Ms: 2044.8,
    maxErrorRate: 0.0,
    scaleUpCount: 4,
    scaleDownCount: 0,
    holdCount: 125,
    bottlenecksDetected: 60,
    clusterModified: false,
    actuatorMode: "DRY_RUN",
    users: 80,
    notes: "Live Stage 8.5 E03 sudden traffic spike (5 -> 80 -> 5 users @ 20 u/s, 120s)",
    tags: ["stage-8.5", "e03", "sudden-spike", "live-run"],
    totalDecisions: 129,
    totalEvaluations: 13,
  },
  {
    id: "exp_20261110T172135_sustained_high_traffic_51ce3165",
    profile: "SUSTAINED_HIGH_TRAFFIC",
    displayName: "Profile 4: Sustained High Traffic (Saturation)",
    status: "COMPLETED",
    createdAt: "2026-11-10T17:21:35.936855+00:00",
    startedAt: "2026-11-10T17:21:35.946191+00:00",
    endedAt: "2026-11-10T17:25:26.355577+00:00",
    durationSeconds: 230.1,
    targetDurationSeconds: 220,
    avgFrontendRps: 50.02,
    peakFrontendRps: 66.11,
    avgFrontendP95Ms: 208.6,
    maxFrontendP95Ms: 364.86,
    maxErrorRate: 0.0017,
    scaleUpCount: 7,
    scaleDownCount: 0,
    holdCount: 219,
    bottlenecksDetected: 80,
    clusterModified: false,
    actuatorMode: "DRY_RUN",
    users: 60,
    notes: "Live Stage 8 E04 sustained high traffic (60 users @ 5 u/s, 180s plateau, 220s total)",
    tags: ["stage-8", "e04", "sustained-high-traffic", "live-run"],
    totalDecisions: 226,
    totalEvaluations: 23,
  },
  {
    id: "exp_20261110T172806_traffic_decrease_71144bfe",
    profile: "TRAFFIC_DECREASE",
    displayName: "Profile 5: Traffic Decrease",
    status: "COMPLETED",
    createdAt: "2026-11-10T17:28:06.396434+00:00",
    startedAt: "2026-11-10T17:28:06.402450+00:00",
    endedAt: "2026-11-10T17:31:16.726903+00:00",
    durationSeconds: 190,
    targetDurationSeconds: 180,
    avgFrontendRps: 24.88,
    peakFrontendRps: 54.0,
    avgFrontendP95Ms: 165.88,
    maxFrontendP95Ms: 246.59,
    maxErrorRate: 0.0012,
    scaleUpCount: 0,
    scaleDownCount: 0,
    holdCount: 182,
    bottlenecksDetected: 40,
    clusterModified: false,
    actuatorMode: "DRY_RUN",
    users: 50,
    notes: "Live Stage 8 E05 traffic decrease (50 -> 25 -> 5 users @ 5 u/s, 180s total)",
    tags: ["stage-8", "e05", "traffic-decrease", "live-run"],
    totalDecisions: 182,
    totalEvaluations: 19,
  },
  {
    id: "exp_20261110T173312_bursty_traffic_55733a14",
    profile: "BURSTY_TRAFFIC",
    displayName: "Profile 6: Bursty Traffic",
    status: "COMPLETED",
    createdAt: "2026-11-10T17:33:12.393268+00:00",
    startedAt: "2026-11-10T17:33:12.406520+00:00",
    endedAt: "2026-11-10T17:36:02.740579+00:00",
    durationSeconds: 170,
    targetDurationSeconds: 160,
    avgFrontendRps: 32.39,
    peakFrontendRps: 46.54,
    avgFrontendP95Ms: 825.31,
    maxFrontendP95Ms: 1875.63,
    maxErrorRate: 0.0015,
    scaleUpCount: 8,
    scaleDownCount: 0,
    holdCount: 160,
    bottlenecksDetected: 150,
    clusterModified: false,
    actuatorMode: "DRY_RUN",
    users: 60,
    notes: "Live Stage 8 E06 bursty traffic (4 cycles of 60u/5u @ 20 u/s, 160s total)",
    tags: ["stage-8", "e06", "bursty-traffic", "live-run"],
    totalDecisions: 168,
    totalEvaluations: 17,
  },
];

// ---------------------------------------------------------------------
// STAGE 9 COMPREHENSIVE COMPARATIVE EVALUATION DATASET (OFFLINE TRACE REPLAY)
// ---------------------------------------------------------------------
export interface PolicyEvaluationRecord {
  policyId: string;
  policyName: string;
  category: "BASELINE" | "PROPOSED";
  description: string;
  totalEvaluations: number;
  holdCount: number;
  holdPercent: number;
  scaleUpCount: number;
  scaleUpPercent: number;
  scaleDownCount: number;
  scaleDownPercent: number;
  decisionStability: number;
  actionFrequency: number;
  e02DetectionTimeSec: number | null;
  e03DetectionTimeSec: number | null;
  e06FlappingCount: number;
  e05FloorBreaches: number;
  bottleneckTargetingRatio: number;
  misdirectedLeafScaleUps: number;
  maxReplicasProposed: number;
  notes: string;
}

export const STAGE_9_POLICIES: PolicyEvaluationRecord[] = [
  {
    policyId: "STATIC",
    policyName: "Static Allocation (Control)",
    category: "BASELINE",
    description: "Fixed single-replica allocation (non-scaling control baseline)",
    totalEvaluations: 1050,
    holdCount: 1050,
    holdPercent: 100.0,
    scaleUpCount: 0,
    scaleUpPercent: 0.0,
    scaleDownCount: 0,
    scaleDownPercent: 0.0,
    decisionStability: 100.0,
    actionFrequency: 0.0,
    e02DetectionTimeSec: null,
    e03DetectionTimeSec: null,
    e06FlappingCount: 0,
    e05FloorBreaches: 0,
    bottleneckTargetingRatio: 0.0,
    misdirectedLeafScaleUps: 0,
    maxReplicasProposed: 1,
    notes: "Zero elasticity; severe queuing delays under high saturation.",
  },
  {
    policyId: "CPU_THRESHOLD",
    policyName: "CPU-Threshold Reactive",
    category: "BASELINE",
    description: "Dual watermark (70% up / 30% down) with 30s cooldown",
    totalEvaluations: 1050,
    holdCount: 988,
    holdPercent: 94.1,
    scaleUpCount: 27,
    scaleUpPercent: 2.6,
    scaleDownCount: 3,
    scaleDownPercent: 0.3,
    decisionStability: 94.1,
    actionFrequency: 2.86,
    e02DetectionTimeSec: 160.0,
    e03DetectionTimeSec: 80.0,
    e06FlappingCount: 2,
    e05FloorBreaches: 1,
    bottleneckTargetingRatio: 48.1,
    misdirectedLeafScaleUps: 14,
    maxReplicasProposed: 10,
    notes: "Significant detection lag; 14 misdirected scale-ups to low-CPU leaf services.",
  },
  {
    policyId: "HPA_STYLE",
    policyName: "Kubernetes HPA-Style",
    category: "BASELINE",
    description: "Proportional CPU target (70% ratio) with 60s stabilization",
    totalEvaluations: 1050,
    holdCount: 984,
    holdPercent: 93.7,
    scaleUpCount: 34,
    scaleUpPercent: 3.2,
    scaleDownCount: 0,
    scaleDownPercent: 0.0,
    decisionStability: 93.7,
    actionFrequency: 3.24,
    e02DetectionTimeSec: 150.0,
    e03DetectionTimeSec: 70.0,
    e06FlappingCount: 0,
    e05FloorBreaches: 0,
    bottleneckTargetingRatio: 61.8,
    misdirectedLeafScaleUps: 13,
    maxReplicasProposed: 10,
    notes: "Aggressive multi-step scaling; hits 10-replica ceiling in burst profiles.",
  },
  {
    policyId: "DPBPS",
    policyName: "DPBPS (Proposed Framework)",
    category: "PROPOSED",
    description: "Multi-dimensional pressure + CI/CD phase awareness + bottleneck prioritization",
    totalEvaluations: 1050,
    holdCount: 991,
    holdPercent: 94.4,
    scaleUpCount: 27,
    scaleUpPercent: 2.6,
    scaleDownCount: 0,
    scaleDownPercent: 0.0,
    decisionStability: 94.4,
    actionFrequency: 2.57,
    e02DetectionTimeSec: 10.0,
    e03DetectionTimeSec: 50.0,
    e06FlappingCount: 0,
    e05FloorBreaches: 0,
    bottleneckTargetingRatio: 96.3,
    misdirectedLeafScaleUps: 0,
    maxReplicasProposed: 8,
    notes: "Rapid detection velocity (10s in E02); 0 misdirected leaf scale-ups; zero flapping.",
  },
];
