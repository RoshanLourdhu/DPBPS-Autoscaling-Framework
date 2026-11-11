// src/pages/ServicesPage.tsx
import { useEffect, useState } from "react";
import { fetchServices } from "../services/api";
import type { ServiceInfo } from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { RefreshCw, Network } from "lucide-react";

export default function ServicesPage() {
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const data = await fetchServices();
      setServices(data);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load services inventory.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState />;
  if (error && services.length === 0) return <ErrorState message={error} />;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <PageHeader
          title="Online Boutique Microservices Inventory"
          subtitle="Real-time application telemetry and call-graph dependencies"
        />
        <button
          onClick={loadData}
          className="flex items-center space-x-1 px-3 py-1.5 text-xs font-medium rounded bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 shadow-sm"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {services.map((svc) => (
          <div
            key={svc.id}
            className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm flex flex-col justify-between space-y-4 hover:border-blue-300 transition-colors"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-gray-900">{svc.name}</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    svc.health === "HEALTHY"
                      ? "bg-green-100 text-green-800"
                      : "bg-red-100 text-red-800"
                  }`}
                >
                  {svc.health}
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Namespace: <span className="font-mono text-gray-700">{svc.environment_id}</span>
              </div>

              {/* Metrics grid */}
              <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-gray-100 text-xs">
                <div>
                  <div className="text-gray-400 text-[11px]">Request Rate</div>
                  <div className="font-mono font-semibold text-gray-800">
                    {svc.request_rate.toFixed(1)} req/s
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-[11px]">P95 Latency</div>
                  <div className="font-mono font-semibold text-gray-800">
                    {svc.p95_latency.toFixed(1)} ms
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-[11px]">CPU Util.</div>
                  <div className="font-mono font-semibold text-gray-800">
                    {(svc.cpu_utilisation * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-[11px]">Memory Util.</div>
                  <div className="font-mono font-semibold text-gray-800">
                    {(svc.memory_utilisation * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-[11px]">Error Rate</div>
                  <div className="font-mono font-semibold text-gray-800">
                    {(svc.error_rate * 100).toFixed(2)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 text-[11px]">Replicas (Ready/Des)</div>
                  <div className="font-mono font-semibold text-gray-800">
                    {svc.ready_replicas} / {svc.desired_replicas ?? svc.ready_replicas}
                  </div>
                </div>
              </div>
            </div>

            {/* Dependencies */}
            <div className="pt-2 border-t border-gray-100">
              <div className="text-[11px] font-semibold text-gray-500 flex items-center space-x-1 mb-1">
                <Network className="h-3 w-3 text-gray-400" />
                <span>Downstream Dependencies ({svc.dependencies?.length ?? 0}):</span>
              </div>
              {svc.dependencies && svc.dependencies.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {svc.dependencies.map((dep) => (
                    <span
                      key={dep}
                      className="px-1.5 py-0.5 rounded text-[10px] bg-gray-100 text-gray-700 font-mono"
                    >
                      {dep}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-[11px] text-gray-400 italic">Leaf service (no downstream calls)</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
