// src/pages/OverviewDashboard.tsx
import { useEffect, useState } from "react";
import { fetchHealth, fetchOverviewMetrics, fetchEnvironments, fetchScalingEvents, fetchDeployments } from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { ChartContainer } from "../components/ui/ChartContainer";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";

import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";

interface Metric {
  name: string;
  value: number;
  unit: string;
  timestamp: string;
  environment_id: string;
  service_id?: string;
  source: string;
  simulated: boolean;
}

export default function OverviewDashboard() {
  const [health, setHealth] = useState<any>(null);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [environments, setEnvironments] = useState<any[]>([]);
  
  const [scalingEvents, setScalingEvents] = useState<any[]>([]);
  const [deployments, setDeployments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadAll() {
      try {
        const [h, m, env, events, deps] = await Promise.all([
          fetchHealth(),
          fetchOverviewMetrics(),
          fetchEnvironments(),
          fetchScalingEvents(),
          fetchDeployments(),
        ]);
        setHealth(h);
        setMetrics(m.metrics ?? []);
        setEnvironments(env);
        
        setScalingEvents(events);
        setDeployments(deps);
      } catch (e: any) {
        setError(e.message || "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    loadAll();
  }, []);

  // Helper to aggregate demo metrics if none are returned
  const demoMetrics: Record<string, { value: number; unit: string }> = {
    "request_rate": { value: 1250, unit: "req/s" },
    "p95_latency": { value: 210, unit: "ms" },
    "error_rate": { value: 0.02, unit: "%" },
    "cpu_utilisation": { value: 68, unit: "%" },
    "memory_utilisation": { value: 71, unit: "%" },
    "ready_replicas": { value: 8, unit: "" },
  };

  const getMetric = (name: string) => {
    const found = metrics.find((m) => m.name === name);
    if (found) return { value: found.value, unit: found.unit };
    const demo = demoMetrics[name];
    return { value: demo?.value ?? "N/A", unit: demo?.unit ?? "" };
  };

  const chartDemoData = Array.from({ length: 10 }, (_, i) => ({
    time: `${i}s`,
    request_rate: Math.round(800 + Math.random() * 400),
    p95_latency: Math.round(180 + Math.random() * 50),
    cpu: Math.round(50 + Math.random() * 30),
    memory: Math.round(55 + Math.random() * 25),
  }));

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Overview Dashboard" subtitle="DPBPS research platform" />

      {/* Health */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Backend" value={health?.status ?? "unknown"} demo={false} />
        <MetricCard title="Environments" value={environments.length} demo={false} />
        <MetricCard title="Deployments" value={deployments.length} demo={false} />
        <MetricCard title="Scaling Events" value={scalingEvents.length} demo={false} />
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 mt-4">
        <MetricCard title="Request Rate" value={getMetric("request_rate").value} unit={getMetric("request_rate").unit} demo={metrics.length === 0} />
        <MetricCard title="P95 Latency" value={getMetric("p95_latency").value} unit={getMetric("p95_latency").unit} demo={metrics.length === 0} />
        <MetricCard title="Error Rate" value={getMetric("error_rate").value} unit={getMetric("error_rate").unit} demo={metrics.length === 0} />
        <MetricCard title="CPU Utilisation" value={getMetric("cpu_utilisation").value} unit={getMetric("cpu_utilisation").unit} demo={metrics.length === 0} />
        <MetricCard title="Memory Utilisation" value={getMetric("memory_utilisation").value} unit={getMetric("memory_utilisation").unit} demo={metrics.length === 0} />
        <MetricCard title="Ready Replicas" value={getMetric("ready_replicas").value} unit={getMetric("ready_replicas").unit} demo={metrics.length === 0} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
        <ChartContainer title="Request Rate Over Time" demo={metrics.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartDemoData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="request_rate" stroke="#0ea5e9" />
            </LineChart>
          </ResponsiveContainer>
        </ChartContainer>
        <ChartContainer title="P95 Latency Over Time" demo={metrics.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartDemoData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="p95_latency" stroke="#1e40af" />
            </LineChart>
          </ResponsiveContainer>
        </ChartContainer>
        <ChartContainer title="CPU & Memory Utilisation" demo={metrics.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartDemoData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="cpu" stroke="#0ea5e9" name="CPU %" />
              <Line type="monotone" dataKey="memory" stroke="#1e40af" name="Memory %" />
            </LineChart>
          </ResponsiveContainer>
        </ChartContainer>
      </div>
    </div>
  );
}
