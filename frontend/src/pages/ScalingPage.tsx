// src/pages/ScalingPage.tsx
import { useEffect, useState } from "react";
import {
  fetchScalingStatus,
  fetchScalingDecisions,
  fetchActuatorHistory,
} from "../services/api";
import type {
  ScalingStatusResponse,
  DecisionRecord,
  ActuatorResult,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { ShieldCheck, RefreshCw, Sliders, History } from "lucide-react";

export default function ScalingPage() {
  const [status, setStatus] = useState<ScalingStatusResponse | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [actuatorHistory, setActuatorHistory] = useState<ActuatorResult[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [st, decs, act] = await Promise.all([
        fetchScalingStatus(),
        fetchScalingDecisions(20),
        fetchActuatorHistory(20),
      ]);
      setStatus(st);
      setDecisions(decs);
      setActuatorHistory(act);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load scaling telemetry.");
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
  if (error && !status) return <ErrorState message={error} />;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <PageHeader
          title="Scaling Control & Actuator History"
          subtitle="DPBPS Controller Parameters, Invariant Checks, and Dry-Run Audit Trails"
        />
        <div className="flex items-center space-x-2 text-xs text-gray-500">
          <span>Decisions logged: {decisions.length}</span>
          <span>&bull;</span>
          <button
            onClick={loadData}
            className="flex items-center space-x-1 px-3 py-1.5 font-medium rounded bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 shadow-sm"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Refresh History</span>
          </button>
        </div>
      </div>

      {/* Safety Notice */}
      <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r shadow-sm flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <ShieldCheck className="h-5 w-5 text-amber-600 flex-shrink-0" />
          <div className="text-xs text-amber-800">
            <span className="font-bold">Actuator Safety Posture:</span> DRY-RUN Active. Live scaling disabled (<code className="font-mono">SCALING_ENABLED=false</code>).
            No Kubernetes scale mutations occur.
          </div>
        </div>
        <span className="text-xs font-semibold px-2 py-0.5 rounded bg-amber-200 text-amber-900">
          DRY_RUN
        </span>
      </div>

      {/* Controller Parameters */}
      <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
        <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center space-x-2 mb-4">
          <Sliders className="h-4 w-4 text-blue-600" />
          <span>DPBPS Algorithmic Scaling Parameters</span>
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="p-3 bg-gray-50 rounded border border-gray-100">
            <div className="text-gray-500 font-medium">Replica Bounds</div>
            <div className="text-sm font-bold text-gray-900 mt-1">
              [{status?.config.min_replicas ?? 1}, {status?.config.max_replicas ?? 10}]
            </div>
            <div className="text-[10px] text-gray-400 mt-0.5">Min / Max allowed</div>
          </div>
          <div className="p-3 bg-gray-50 rounded border border-gray-100">
            <div className="text-gray-500 font-medium">CPU Threshold</div>
            <div className="text-sm font-bold text-gray-900 mt-1">
              {((status?.config.cpu_threshold ?? 0.8) * 100).toFixed(0)}%
            </div>
            <div className="text-[10px] text-gray-400 mt-0.5">Scale-up trigger</div>
          </div>
          <div className="p-3 bg-gray-50 rounded border border-gray-100">
            <div className="text-gray-500 font-medium">Memory Threshold</div>
            <div className="text-sm font-bold text-gray-900 mt-1">
              {((status?.config.memory_threshold ?? 0.8) * 100).toFixed(0)}%
            </div>
            <div className="text-[10px] text-gray-400 mt-0.5">Scale-up trigger</div>
          </div>
          <div className="p-3 bg-gray-50 rounded border border-gray-100">
            <div className="text-gray-500 font-medium">Latency Target</div>
            <div className="text-sm font-bold text-gray-900 mt-1">
              {status?.config.latency_target_ms ?? 200} ms
            </div>
            <div className="text-[10px] text-gray-400 mt-0.5">SLA boundary</div>
          </div>
        </div>
      </div>

      {/* Actuator Execution Audit Trail */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center space-x-2">
            <History className="h-4 w-4 text-purple-600" />
            <span>Kubernetes Scaling Actuator Dry-Run Audit Log</span>
          </h3>
          <span className="text-xs text-gray-500">Last {actuatorHistory.length} evaluations</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-xs">
            <thead className="bg-gray-50 text-gray-600 font-semibold uppercase">
              <tr>
                <th scope="col" className="px-4 py-3 text-left">Service</th>
                <th scope="col" className="px-3 py-3 text-center">Action</th>
                <th scope="col" className="px-3 py-3 text-center">Replicas (Prev &rarr; Req)</th>
                <th scope="col" className="px-3 py-3 text-center">Status</th>
                <th scope="col" className="px-3 py-3 text-center">Cluster Modified</th>
                <th scope="col" className="px-4 py-3 text-left">Reason / Invariant Check</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {actuatorHistory.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                    No actuator history recorded yet. Trigger pipeline evaluation from Overview.
                  </td>
                </tr>
              ) : (
                actuatorHistory.map((item, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900 whitespace-nowrap">
                      {item.service_name}
                    </td>
                    <td className="px-3 py-3 text-center whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded font-bold text-[10px] bg-gray-100 text-gray-800">
                        {item.action}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-center whitespace-nowrap font-mono">
                      {item.current_replicas} &rarr; {item.requested_replicas}
                    </td>
                    <td className="px-3 py-3 text-center whitespace-nowrap">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          item.status === "VALIDATED"
                            ? "bg-green-100 text-green-800"
                            : item.status === "REJECTED"
                            ? "bg-red-100 text-red-800"
                            : "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-center whitespace-nowrap">
                      <span className="text-gray-500 font-mono">
                        {item.cluster_modified ? "True" : "False (Guarded)"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 max-w-sm truncate" title={item.reason}>
                      {item.reason}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
