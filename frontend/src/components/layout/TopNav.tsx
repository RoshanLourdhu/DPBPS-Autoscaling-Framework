// src/components/layout/TopNav.tsx
import React, { useEffect, useState, useCallback } from "react";
import { useLocation } from "react-router-dom";
import {
  RefreshCw,
  Server,
  Layers,
  Activity,
  ShieldCheck,
  Menu,
  Lock,
} from "lucide-react";
import type { HealthResponse } from "../../services/api";
import { fetchHealth } from "../../services/api";

const routeTitles: Record<string, { title: string; category: string }> = {
  "/": { title: "Executive Overview", category: "Observability" },
  "/services": { title: "Microservices Monitoring", category: "Workloads" },
  "/topology": { title: "Service Call-Graph Topology", category: "Topology" },
  "/bottlenecks": { title: "Bottleneck Analysis", category: "Diagnosis" },
  "/intelligence": { title: "DPBPS Intelligence Center", category: "Algorithms" },
  "/deployments": { title: "Deployment Intelligence", category: "CI/CD Lifecycle" },
  "/experiments": { title: "Workload Experiments", category: "Evaluation" },
  "/analytics": { title: "Comparative Performance Analytics", category: "Research" },
  "/scaling": { title: "Actuator Scaling History", category: "Audit & Safety" },
  "/settings": { title: "System Configuration", category: "Control Plane" },
  "/environments": { title: "Environment Inventory", category: "Infrastructure" },
  "/workloads": { title: "Workload Profiles", category: "Workloads" },
};

export interface TopNavProps {
  onMobileToggle?: () => void;
  onRefresh?: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({ onMobileToggle, onRefresh }) => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");
  const location = useLocation();

  const loadHealth = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const data = await fetchHealth();
      setHealth(data);
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch {
      setHealth(null);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadHealth();
    const interval = setInterval(loadHealth, 15000);
    return () => clearInterval(interval);
  }, [loadHealth]);

  const handleRefreshClick = () => {
    loadHealth();
    onRefresh?.();
  };

  const currentMeta = routeTitles[location.pathname] || {
    title: "Observability Platform",
    category: "DPBPS",
  };

  const isBackendConnected = health?.status === "ok";
  const isK8sConnected = health?.kubernetes_connected === true;
  const isPromConnected = health?.prometheus_connected === true;

  return (
    <header className="h-14 bg-canvas-card border-b border-canvas-border px-4 sm:px-6 flex items-center justify-between gap-4 sticky top-0 z-30 flex-shrink-0">
      {/* Left: Mobile Toggle & Breadcrumbs */}
      <div className="flex items-center space-x-3 min-w-0">
        {onMobileToggle && (
          <button
            onClick={onMobileToggle}
            className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-canvas-hover lg:hidden"
            aria-label="Open sidebar"
          >
            <Menu size={18} />
          </button>
        )}

        <div className="flex items-center space-x-2 text-xs truncate">
          <span className="text-text-muted hidden sm:inline">Platform</span>
          <span className="text-text-muted hidden sm:inline">/</span>
          <span className="text-text-secondary font-medium hidden md:inline">
            {currentMeta.category}
          </span>
          <span className="text-text-muted hidden md:inline">/</span>
          <h1 className="text-sm font-semibold text-text-primary truncate">
            {currentMeta.title}
          </h1>
        </div>
      </div>

      {/* Right: Telemetry Invariants & Status Badges */}
      <div className="flex items-center space-x-2 sm:space-x-3 flex-shrink-0 text-xs">
        {/* Backend Status */}
        <div
          className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-md border font-mono ${
            isBackendConnected
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : "bg-rose-500/10 text-rose-400 border-rose-500/20"
          }`}
          title={isBackendConnected ? "FastAPI Backend Connected" : "Backend Disconnected"}
        >
          <Server size={12} />
          <span className="hidden sm:inline">API:</span>
          <span>{isBackendConnected ? "ONLINE" : "OFFLINE"}</span>
        </div>

        {/* Kubernetes Connection Status */}
        <div
          className={`hidden md:flex items-center space-x-1.5 px-2.5 py-1 rounded-md border font-mono ${
            isK8sConnected
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : "bg-slate-800 text-slate-400 border-slate-700"
          }`}
          title={isK8sConnected ? "Kubernetes API Connected (Docker Desktop)" : "Kubernetes Not Connected"}
        >
          <Layers size={12} />
          <span>K8S:</span>
          <span>{isK8sConnected ? "ACTIVE" : "DISCONN"}</span>
        </div>

        {/* Prometheus Status */}
        <div
          className={`hidden lg:flex items-center space-x-1.5 px-2.5 py-1 rounded-md border font-mono ${
            isPromConnected
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : "bg-amber-500/10 text-amber-400 border-amber-500/20"
          }`}
          title={isPromConnected ? "Prometheus Metrics Scraper Online" : "Prometheus Scraper Unreachable"}
        >
          <Activity size={12} />
          <span>PROM:</span>
          <span>{isPromConnected ? "READY" : "NO_DATA"}</span>
        </div>

        {/* Operating Posture (DRY-RUN Verified) */}
        <div
          className="flex items-center space-x-1.5 px-2.5 py-1 rounded-md border bg-amber-500/10 text-amber-400 border-amber-500/30 font-mono font-semibold"
          title="Cluster Safety Invariant: Actuator operates in DRY-RUN mode. Cluster mutations inhibited."
        >
          <ShieldCheck size={13} className="text-amber-400" />
          <span>DRY_RUN</span>
        </div>

        {/* Live Scaling Invariant */}
        <div
          className="hidden xl:flex items-center space-x-1 px-2 py-1 rounded-md bg-slate-800 text-slate-400 border border-slate-700 font-mono text-[11px]"
          title="Safety lock: SCALING_ENABLED=false in configuration"
        >
          <Lock size={11} className="text-slate-400" />
          <span>SCALING: OFF</span>
        </div>

        {/* Refresh Button */}
        <button
          onClick={handleRefreshClick}
          disabled={isRefreshing}
          className="p-1.5 rounded-lg border border-canvas-border bg-canvas-elevated hover:bg-canvas-hover text-text-secondary hover:text-text-primary disabled:opacity-50 transition-colors"
          title={`Refresh telemetry (Last: ${lastRefreshed || "just now"})`}
        >
          <RefreshCw size={14} className={isRefreshing ? "animate-spin text-cyan-400" : ""} />
        </button>
      </div>
    </header>
  );
};
