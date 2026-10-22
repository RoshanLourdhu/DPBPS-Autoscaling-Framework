// src/services/api.ts
/** API service helpers for the DPBPS frontend */
export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/** Helper to build full URL */
function url(path: string): string {
  return `${API_BASE}${path}`;
}

/** Generic fetch wrapper */
async function request<T>(path: string): Promise<T> {
  const resp = await fetch(url(path));
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`API error ${resp.status}: ${err}`);
  }
  return (await resp.json()) as T;
}

// Health endpoint
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}
export const fetchHealth = () => request<HealthResponse>("/api/v1/health");

// Environments
export interface EnvironmentInfo {
  id: string;
  name: string;
  description?: string;
  status: string;
}
export const fetchEnvironments = () => request<EnvironmentInfo[]>("/api/v1/environments");

// Overview metrics
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

// Scaling config
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

// Services
export interface ServiceInfo {
  id: string;
  name: string;
  environment_id: string;
  health: string;
  ready_replicas: number;
  cpu_utilisation: number;
  memory_utilisation: number;
  request_rate: number;
  p95_latency: number;
  error_rate: number;
}
export const fetchServices = () => request<ServiceInfo[]>("/api/v1/services");

// Scaling events
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

// Deployments
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

// Experiments
export interface ExperimentInfo {
  id: string;
  name: string;
  environment_id: string;
  scaling_strategy: string;
  workload_scenario: string;
  duration_seconds: number;
  configuration: Record<string, any>;
  status: string;
  start_timestamp?: string;
  end_timestamp?: string;
}
export const fetchExperiments = () => request<ExperimentInfo[]>("/api/v1/experiments");
