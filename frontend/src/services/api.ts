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
}
export const fetchScalingStatus = () => request<ScalingStatusResponse>("/api/v1/scaling/status");

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

export const updateDeploymentPhase = (phase: string) =>
  postRequest<{ phase: string }>("/api/v1/scaling/deployment-phase", { phase });

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
