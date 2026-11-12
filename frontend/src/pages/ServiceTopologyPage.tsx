// src/pages/ServiceTopologyPage.tsx
import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import {
  fetchServices,
  fetchPipelineEvaluation,
} from "../services/api";
import type {
  ServiceInfo,
  PipelineEvaluationResponse,
  PipelineServiceResult,
} from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { MetricCard } from "../components/ui/MetricCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import {
  Network,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Activity,
  Flame,
  ArrowRight,
  ArrowDownRight,
  X,
  ShieldCheck,
  RefreshCw,
  Search,
} from "lucide-react";

interface NodePosition {
  id: string;
  label: string;
  tier: number;
  tierLabel: string;
  role: string;
  x: number;
  y: number;
}

// 4-Tier Logical Layout for Online Boutique
const TOPOLOGY_NODES: NodePosition[] = [
  // Tier 1: Client Ingress
  {
    id: "frontend",
    label: "frontend",
    tier: 1,
    tierLabel: "Tier 1: Ingress",
    role: "HTTP Ingress & Edge Proxy",
    x: 40,
    y: 280,
  },

  // Tier 2: Domain Orchestration & Aggregation
  {
    id: "checkoutservice",
    label: "checkoutservice",
    tier: 2,
    tierLabel: "Tier 2: Orchestration",
    role: "Checkout Flow Coordinator",
    x: 300,
    y: 130,
  },
  {
    id: "recommendationservice",
    label: "recommendationservice",
    tier: 2,
    tierLabel: "Tier 2: Orchestration",
    role: "ML Product Recommendations",
    x: 300,
    y: 440,
  },

  // Tier 3: State & Session Storage
  {
    id: "cartservice",
    label: "cartservice",
    tier: 3,
    tierLabel: "Tier 3: State",
    role: "Shopping Cart State Store",
    x: 570,
    y: 70,
  },

  // Tier 4: Core Domain & Downstream Leaf Services
  {
    id: "productcatalogservice",
    label: "productcatalogservice",
    tier: 4,
    tierLabel: "Tier 4: Core Domain",
    role: "Product Inventory & Details",
    x: 850,
    y: 30,
  },
  {
    id: "currencyservice",
    label: "currencyservice",
    tier: 4,
    tierLabel: "Tier 4: Core Domain",
    role: "Currency Exchange Rates",
    x: 850,
    y: 130,
  },
  {
    id: "paymentservice",
    label: "paymentservice",
    tier: 4,
    tierLabel: "Tier 4: Core Domain",
    role: "Payment Authorization",
    x: 850,
    y: 230,
  },
  {
    id: "shippingservice",
    label: "shippingservice",
    tier: 4,
    tierLabel: "Tier 4: Core Domain",
    role: "Shipping Quote & Fulfillment",
    x: 850,
    y: 330,
  },
  {
    id: "emailservice",
    label: "emailservice",
    tier: 4,
    tierLabel: "Tier 4: Core Domain",
    role: "Order Notification Dispatcher",
    x: 850,
    y: 430,
  },
  {
    id: "adservice",
    label: "adservice",
    tier: 4,
    tierLabel: "Tier 4: Core Domain",
    role: "Targeted Ad Serving",
    x: 850,
    y: 530,
  },
];

// Authoritative 14 Directed Call Edges from ONLINE_BOUTIQUE_DEPENDENCIES
const CALL_EDGES: [string, string][] = [
  ["frontend", "checkoutservice"],
  ["frontend", "recommendationservice"],
  ["frontend", "cartservice"],
  ["frontend", "productcatalogservice"],
  ["frontend", "currencyservice"],
  ["frontend", "shippingservice"],
  ["frontend", "adservice"],
  ["checkoutservice", "cartservice"],
  ["checkoutservice", "productcatalogservice"],
  ["checkoutservice", "currencyservice"],
  ["checkoutservice", "paymentservice"],
  ["checkoutservice", "shippingservice"],
  ["checkoutservice", "emailservice"],
  ["recommendationservice", "productcatalogservice"],
];

const NODE_WIDTH = 166;
const NODE_HEIGHT = 58;

export default function ServiceTopologyPage() {
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [pipeline, setPipeline] = useState<PipelineEvaluationResponse | null>(null);
  const [selectedService, setSelectedService] = useState<ServiceInfo | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "BOTTLENECK" | "PRESSURE" | "HEALTHY">("ALL");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  // Canvas Pan & Zoom State
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const svgContainerRef = useRef<HTMLDivElement>(null);

  const loadData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [svcData, pipeData] = await Promise.all([
        fetchServices(),
        fetchPipelineEvaluation(),
      ]);
      setServices(svcData);
      setPipeline(pipeData);
      setLastRefreshed(new Date().toLocaleTimeString());
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load service topology data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(false), 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  const bottleneckService = pipeline?.bottleneck_service;
  const serviceMap = useMemo(() => new Map(services.map((s) => [s.name, s])), [services]);
  const nodeMap = useMemo(() => new Map(TOPOLOGY_NODES.map((n) => [n.id, n])), []);

  // Map pipeline evaluation decisions by service name
  const decisionMap = useMemo(() => {
    const map = new Map<string, PipelineServiceResult>();
    if (pipeline?.services) {
      pipeline.services.forEach((ps) => map.set(ps.service_name, ps));
    }
    return map;
  }, [pipeline]);

  // Inverted Call Graph: Map each service to incoming callers
  const incomingMap = useMemo(() => {
    const map: Record<string, string[]> = {};
    TOPOLOGY_NODES.forEach((n) => {
      map[n.id] = [];
    });
    CALL_EDGES.forEach(([from, to]) => {
      if (!map[to]) map[to] = [];
      if (!map[to].includes(from)) map[to].push(from);
    });
    return map;
  }, []);

  // Pan & Zoom Handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).tagName === "svg" || (e.target as HTMLElement).tagName === "rect") {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.08 : -0.08;
    setZoom((prev) => Math.min(1.8, Math.max(0.65, prev + delta)));
  };

  const handleResetView = () => {
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
    setSelectedService(null);
    setHoveredNodeId(null);
  };

  const activeFocusId = selectedService?.name || hoveredNodeId;

  // Determine Node Status Severity
  const getNodeSeverity = useCallback(
    (serviceName: string): "CRITICAL" | "WARNING" | "INSUFFICIENT" | "HEALTHY" => {
      if (serviceName === bottleneckService) return "CRITICAL";
      const svc = serviceMap.get(serviceName);
      const dec = decisionMap.get(serviceName);
      if (svc && !svc.telemetry_available) return "INSUFFICIENT";
      if (dec?.dpbps_decision === "SCALE_UP" || (svc && svc.cpu_utilisation >= 0.7)) return "WARNING";
      return "HEALTHY";
    },
    [bottleneckService, serviceMap, decisionMap]
  );

  // Filtered Nodes Check for Search/Filter Match
  const isNodeHighlighted = useCallback(
    (nodeId: string): boolean => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        if (!nodeId.toLowerCase().includes(q)) return false;
      }
      if (statusFilter === "BOTTLENECK") {
        return nodeId === bottleneckService;
      }
      if (statusFilter === "PRESSURE") {
        return getNodeSeverity(nodeId) === "WARNING";
      }
      if (statusFilter === "HEALTHY") {
        return getNodeSeverity(nodeId) === "HEALTHY";
      }
      return true;
    },
    [searchQuery, statusFilter, bottleneckService, getNodeSeverity]
  );

  if (loading) return <LoadingState message="Constructing interactive microservices topology graph..." />;
  if (error && services.length === 0) return <ErrorState message={error} onRetry={() => loadData(true)} />;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Microservice Call-Graph Topology"
        subtitle="Interactive 4-tier dependency call-graph of the Google Cloud Platform Online Boutique application with directional traffic tracing, bottleneck prioritization, and live container metrics."
        badge={
          <StatusBadge
            status={bottleneckService ? `BOTTLENECK: ${bottleneckService}` : "SYSTEM STABLE"}
            variant={bottleneckService ? "rose" : "emerald"}
            pulse={!!bottleneckService}
          />
        }
        actions={
          <div className="flex items-center space-x-2">
            <button
              onClick={() => loadData(true)}
              disabled={refreshing}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-canvas-border bg-canvas-card hover:bg-canvas-hover text-xs font-medium text-text-secondary hover:text-text-primary disabled:opacity-50 transition-colors"
              title={`Last refreshed: ${lastRefreshed}`}
            >
              <RefreshCw size={13} className={refreshing ? "animate-spin text-cyan-400" : ""} />
              <span>Refresh Topology</span>
            </button>
          </div>
        }
      />

      {/* Summary KPI Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Authoritative Microservices"
          value={TOPOLOGY_NODES.length}
          unit="nodes"
          variant="cyan"
          icon={Network}
          subtext="Google Online Boutique"
          to="/services"
        />
        <MetricCard
          title="Verified Call Edges"
          value={CALL_EDGES.length}
          unit="directed"
          variant="blue"
          icon={Activity}
          subtext="gRPC & HTTP request paths"
        />
        <MetricCard
          title="Active Bottleneck"
          value={bottleneckService || "None"}
          variant={bottleneckService ? "rose" : "emerald"}
          icon={Flame}
          subtext={bottleneckService ? "Prioritized for scale-up" : "Nominal latency across all tiers"}
          to="/bottlenecks"
        />
        <MetricCard
          title="Execution Mode"
          value="DRY_RUN"
          variant="amber"
          icon={ShieldCheck}
          subtext="SCALING_ENABLED=false"
          to="/scaling"
        />
      </div>

      {/* Controls & Filter Bar */}
      <div className="bg-canvas-card border border-canvas-border rounded-xl p-3.5 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Search */}
        <div className="w-full sm:w-72 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter node by name..."
            className="w-full bg-canvas-dark border border-canvas-border rounded-lg pl-9 pr-3 py-1.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-cyan-500/50"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
            >
              <X size={13} />
            </button>
          )}
        </div>

        {/* Status Filters */}
        <div className="flex items-center space-x-1 p-1 rounded-lg bg-canvas-dark border border-canvas-border text-xs">
          <button
            onClick={() => setStatusFilter("ALL")}
            className={`px-2.5 py-1 rounded-md transition-colors ${
              statusFilter === "ALL" ? "bg-canvas-elevated text-text-primary font-semibold" : "text-text-muted hover:text-text-primary"
            }`}
          >
            All (10)
          </button>
          <button
            onClick={() => setStatusFilter("BOTTLENECK")}
            className={`px-2.5 py-1 rounded-md transition-colors ${
              statusFilter === "BOTTLENECK" ? "bg-rose-500/20 text-rose-400 font-semibold" : "text-text-muted hover:text-text-primary"
            }`}
          >
            Bottlenecks
          </button>
          <button
            onClick={() => setStatusFilter("PRESSURE")}
            className={`px-2.5 py-1 rounded-md transition-colors ${
              statusFilter === "PRESSURE" ? "bg-amber-500/20 text-amber-400 font-semibold" : "text-text-muted hover:text-text-primary"
            }`}
          >
            Under Pressure
          </button>
          <button
            onClick={() => setStatusFilter("HEALTHY")}
            className={`px-2.5 py-1 rounded-md transition-colors ${
              statusFilter === "HEALTHY" ? "bg-emerald-500/20 text-emerald-400 font-semibold" : "text-text-muted hover:text-text-primary"
            }`}
          >
            Healthy
          </button>
        </div>

        {/* Graph Controls */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1 p-1 rounded-lg bg-canvas-dark border border-canvas-border text-xs font-mono">
            <button
              onClick={() => setZoom((z) => Math.min(1.8, z + 0.15))}
              className="p-1 rounded hover:bg-canvas-hover text-text-secondary hover:text-text-primary transition-colors"
              title="Zoom In"
            >
              <ZoomIn size={14} />
            </button>
            <span className="px-2 text-text-muted select-none">{(zoom * 100).toFixed(0)}%</span>
            <button
              onClick={() => setZoom((z) => Math.max(0.65, z - 0.15))}
              className="p-1 rounded hover:bg-canvas-hover text-text-secondary hover:text-text-primary transition-colors"
              title="Zoom Out"
            >
              <ZoomOut size={14} />
            </button>
          </div>
          <button
            onClick={handleResetView}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-canvas-dark border border-canvas-border text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
            title="Reset Zoom & Pan to Center"
          >
            <RotateCcw size={13} />
            <span>Reset View</span>
          </button>
        </div>
      </div>

      {/* Main Canvas + Inspector Split View */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 items-start">
        {/* Topology Graph Canvas Container */}
        <div
          ref={svgContainerRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
          className={`xl:col-span-3 bg-canvas-card border border-canvas-border rounded-xl p-4 shadow-card overflow-hidden relative select-none ${
            isDragging ? "cursor-grabbing" : "cursor-grab"
          }`}
          style={{ height: "620px" }}
        >
          {/* Canvas Overlay Header */}
          <div className="absolute top-4 left-4 z-10 flex items-center space-x-3 pointer-events-none">
            <span className="text-xs font-semibold text-text-primary flex items-center space-x-1.5 bg-canvas-dark/80 backdrop-blur-md px-3 py-1 rounded-lg border border-canvas-border">
              <Network size={13} className="text-cyan-400" />
              <span>4-Tier Microservices DAG</span>
            </span>
            <span className="text-[11px] font-mono text-text-muted bg-canvas-dark/80 backdrop-blur-md px-2.5 py-1 rounded-lg border border-canvas-border">
              Drag to pan &bull; Scroll to zoom
            </span>
          </div>

          {/* SVG Canvas */}
          <svg
            viewBox="0 0 1080 620"
            className="w-full h-full"
            style={{ touchAction: "none" }}
          >
            <defs>
              {/* Arrow Head Markers */}
              <marker
                id="arrow-cyan"
                viewBox="0 0 10 10"
                refX="18"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill="#06b6d4" opacity="0.8" />
              </marker>
              <marker
                id="arrow-blue"
                viewBox="0 0 10 10"
                refX="18"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill="#3b82f6" opacity="0.6" />
              </marker>
              <marker
                id="arrow-rose"
                viewBox="0 0 10 10"
                refX="18"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill="#ef4444" />
              </marker>
              <marker
                id="arrow-amber"
                viewBox="0 0 10 10"
                refX="18"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill="#f59e0b" />
              </marker>

              {/* Edge Gradients */}
              <linearGradient id="edgeNormal" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.25" />
              </linearGradient>
              <linearGradient id="edgeActive" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.8" />
              </linearGradient>
              <linearGradient id="edgeCaller" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#fbbf24" stopOpacity="0.8" />
              </linearGradient>
            </defs>

            {/* Transform Group for Pan & Zoom */}
            <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
              {/* Background Tier Column Bands */}
              <g className="tier-bands select-none pointer-events-none opacity-40">
                <rect x="25" y="15" width="200" height="590" rx="12" fill="#0f172a" stroke="#1e293b" strokeDasharray="3 3" />
                <text x="125" y="38" fill="#64748b" fontSize="10" fontWeight="bold" fontFamily="monospace" textAnchor="middle">
                  TIER 1 &bull; INGRESS
                </text>

                <rect x="280" y="15" width="210" height="590" rx="12" fill="#0f172a" stroke="#1e293b" strokeDasharray="3 3" />
                <text x="385" y="38" fill="#64748b" fontSize="10" fontWeight="bold" fontFamily="monospace" textAnchor="middle">
                  TIER 2 &bull; ORCHESTRATION
                </text>

                <rect x="550" y="15" width="210" height="590" rx="12" fill="#0f172a" stroke="#1e293b" strokeDasharray="3 3" />
                <text x="655" y="38" fill="#64748b" fontSize="10" fontWeight="bold" fontFamily="monospace" textAnchor="middle">
                  TIER 3 &bull; STATE STORE
                </text>

                <rect x="830" y="15" width="210" height="590" rx="12" fill="#0f172a" stroke="#1e293b" strokeDasharray="3 3" />
                <text x="935" y="38" fill="#64748b" fontSize="10" fontWeight="bold" fontFamily="monospace" textAnchor="middle">
                  TIER 4 &bull; CORE DOMAIN
                </text>
              </g>

              {/* Directed Call Edges */}
              <g className="edges">
                {CALL_EDGES.map(([fromId, toId], idx) => {
                  const fromNode = nodeMap.get(fromId);
                  const toNode = nodeMap.get(toId);
                  if (!fromNode || !toNode) return null;

                  const x1 = fromNode.x + NODE_WIDTH;
                  const y1 = fromNode.y + NODE_HEIGHT / 2;
                  const x2 = toNode.x;
                  const y2 = toNode.y + NODE_HEIGHT / 2;
                  const dx = x2 - x1;
                  const cx1 = x1 + dx * 0.45;
                  const cy1 = y1;
                  const cx2 = x2 - dx * 0.45;
                  const cy2 = y2;
                  const pathData = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;

                  const isBottleneckEdge = toId === bottleneckService;
                  const isIncomingToActive = activeFocusId && toId === activeFocusId;
                  const isOutgoingFromActive = activeFocusId && fromId === activeFocusId;
                  const isConnectedToActive = isIncomingToActive || isOutgoingFromActive;
                  const isDimmed = activeFocusId && !isConnectedToActive;

                  let strokeColor = "url(#edgeNormal)";
                  let strokeWidth = 1.5;
                  let strokeDash = undefined;
                  let marker = "url(#arrow-blue)";

                  if (isBottleneckEdge) {
                    strokeColor = "#ef4444";
                    strokeWidth = 2.2;
                    strokeDash = "6 3";
                    marker = "url(#arrow-rose)";
                  } else if (isIncomingToActive) {
                    strokeColor = "url(#edgeCaller)";
                    strokeWidth = 2.5;
                    marker = "url(#arrow-amber)";
                  } else if (isOutgoingFromActive) {
                    strokeColor = "url(#edgeActive)";
                    strokeWidth = 2.5;
                    marker = "url(#arrow-cyan)";
                  }

                  return (
                    <path
                      key={`${fromId}->${toId}-${idx}`}
                      d={pathData}
                      fill="none"
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                      strokeDasharray={strokeDash}
                      markerEnd={marker}
                      opacity={isDimmed ? 0.12 : 1}
                      className="transition-all duration-200"
                    />
                  );
                })}
              </g>

              {/* Topology Nodes */}
              <g className="nodes">
                {TOPOLOGY_NODES.map((node) => {
                  const svc = serviceMap.get(node.id);
                  const severity = getNodeSeverity(node.id);
                  const isBottleneck = severity === "CRITICAL";
                  const isSelected = selectedService?.name === node.id;
                  const isHovered = hoveredNodeId === node.id;
                  const matchesFilter = isNodeHighlighted(node.id);

                  const readyRep = svc?.ready_replicas ?? 1;
                  const desiredRep = svc?.desired_replicas ?? readyRep;
                  const cpuPercent = svc ? ((svc.cpu_utilisation ?? 0) * 100).toFixed(0) : "0";
                  const p95Latency = svc ? (svc.p95_latency ?? 0).toFixed(0) : "0";
                  const isTelemetryDegraded = svc && !svc.telemetry_available;

                  let borderColor = "#1f293d";
                  let cardBg = "#111827";

                  if (isSelected) {
                    borderColor = "#06b6d4";
                    cardBg = "#1e293b";
                  } else if (isBottleneck) {
                    borderColor = "#ef4444";
                    cardBg = "#1f131a";
                  } else if (severity === "WARNING") {
                    borderColor = "#f59e0b";
                  } else if (isHovered) {
                    borderColor = "#38bdf8";
                  }

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      onClick={() => setSelectedService(svc || null)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                      className="cursor-pointer group"
                      opacity={matchesFilter ? 1 : 0.25}
                    >
                      {/* Bottleneck Pulsing Aura */}
                      {isBottleneck && (
                        <rect
                          x="-5"
                          y="-5"
                          width={NODE_WIDTH + 10}
                          height={NODE_HEIGHT + 10}
                          rx="14"
                          fill="none"
                          stroke="#ef4444"
                          strokeWidth="2.5"
                          className="animate-pulse opacity-80"
                        />
                      )}

                      {/* Selected Node Glow Aura */}
                      {isSelected && (
                        <rect
                          x="-4"
                          y="-4"
                          width={NODE_WIDTH + 8}
                          height={NODE_HEIGHT + 8}
                          rx="12"
                          fill="none"
                          stroke="#06b6d4"
                          strokeWidth="2"
                          className="opacity-70"
                        />
                      )}

                      {/* Node Container Card */}
                      <rect
                        x="0"
                        y="0"
                        width={NODE_WIDTH}
                        height={NODE_HEIGHT}
                        rx="10"
                        fill={cardBg}
                        stroke={borderColor}
                        strokeWidth={isSelected || isBottleneck ? 2 : 1.2}
                        className="transition-all duration-150 group-hover:stroke-cyan-400 shadow-md"
                      />

                      {/* Top Row: Severity Indicator + Name */}
                      <circle
                        cx="14"
                        cy="18"
                        r="4"
                        fill={
                          isBottleneck
                            ? "#ef4444"
                            : severity === "WARNING"
                            ? "#f59e0b"
                            : isTelemetryDegraded
                            ? "#94a3b8"
                            : "#10b981"
                        }
                        className={isBottleneck ? "animate-pulse" : ""}
                      />

                      <text
                        x="24"
                        y="22"
                        fill="#f8fafc"
                        fontSize="11"
                        fontWeight="700"
                        fontFamily="Inter, sans-serif"
                      >
                        {node.label.length > 15 ? `${node.label.slice(0, 14)}…` : node.label}
                      </text>

                      {/* Bottleneck Badge Tag */}
                      {isBottleneck && (
                        <g transform={`translate(${NODE_WIDTH - 30}, 8)`}>
                          <rect width="22" height="13" rx="3" fill="#ef4444" fillOpacity="0.2" stroke="#ef4444" strokeWidth="0.8" />
                          <text x="11" y="9.5" fill="#f87171" fontSize="7.5" fontWeight="bold" textAnchor="middle" fontFamily="sans-serif">
                            BOT
                          </text>
                        </g>
                      )}

                      {/* Bottom Row Metrics Ribbon */}
                      <line x1="8" y1="33" x2={NODE_WIDTH - 8} y2="33" stroke="#1e293b" strokeWidth="1" />

                      {/* Replicas Metric */}
                      <text x="12" y="47" fill="#64748b" fontSize="8.5" fontFamily="sans-serif">
                        REP
                      </text>
                      <text x="32" y="47" fill="#38bdf8" fontSize="9" fontWeight="bold" fontFamily="monospace">
                        {readyRep}/{desiredRep}
                      </text>

                      {/* CPU Metric */}
                      <text x="65" y="47" fill="#64748b" fontSize="8.5" fontFamily="sans-serif">
                        CPU
                      </text>
                      <text
                        x="85"
                        y="47"
                        fill={parseInt(cpuPercent) >= 70 ? "#f87171" : "#e2e8f0"}
                        fontSize="9"
                        fontWeight="bold"
                        fontFamily="monospace"
                      >
                        {cpuPercent}%
                      </text>

                      {/* P95 Latency Metric */}
                      <text x="118" y="47" fill="#64748b" fontSize="8.5" fontFamily="sans-serif">
                        P95
                      </text>
                      <text
                        x="136"
                        y="47"
                        fill={parseInt(p95Latency) > 200 ? "#f87171" : "#e2e8f0"}
                        fontSize="9"
                        fontWeight="bold"
                        fontFamily="monospace"
                      >
                        {p95Latency}m
                      </text>
                    </g>
                  );
                })}
              </g>
            </g>
          </svg>

          {/* Canvas Bottom Legend Bar */}
          <div className="absolute bottom-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 p-2 rounded-lg bg-canvas-dark/90 backdrop-blur-md border border-canvas-border text-[11px] text-text-secondary">
            <div className="flex items-center space-x-3">
              <span className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span>Healthy</span>
              </span>
              <span className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span>Under Pressure</span>
              </span>
              <span className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                <span>Identified Bottleneck</span>
              </span>
              <span className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-slate-500" />
                <span>Insufficient Telemetry</span>
              </span>
            </div>
            <div className="flex items-center space-x-3 text-text-muted font-mono">
              <span className="flex items-center space-x-1">
                <span className="w-3 h-0.5 bg-cyan-400" />
                <span>Forward Call Path</span>
              </span>
              <span className="flex items-center space-x-1">
                <span className="w-3 h-0.5 bg-rose-500 border-dashed border-t" />
                <span>Bottleneck Convergence</span>
              </span>
            </div>
          </div>
        </div>

        {/* Node Inspector Side Panel */}
        <div className="bg-canvas-card border border-canvas-border rounded-xl p-5 shadow-card space-y-4">
          <SectionHeader
            title="Service Inspector"
            subtitle="Deep architectural metadata & real-time telemetry"
            icon={Network}
          />

          {selectedService ? (
            <div className="space-y-4 text-xs">
              {/* Header */}
              <div className="flex items-center justify-between pb-3 border-b border-canvas-border">
                <div className="space-y-0.5">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-sm text-text-primary">
                      {selectedService.name}
                    </span>
                    <StatusBadge
                      status={selectedService.health}
                      variant={selectedService.health === "HEALTHY" ? "emerald" : "amber"}
                      size="xs"
                    />
                  </div>
                  <span className="text-[10px] text-text-muted font-mono block">
                    Namespace: {selectedService.environment_id} &bull; Phase: {selectedService.deployment_phase || "NORMAL_OPERATION"}
                  </span>
                </div>
                <button
                  onClick={() => setSelectedService(null)}
                  className="p-1 rounded hover:bg-canvas-hover text-text-muted hover:text-text-primary transition-colors"
                  title="Close Inspector"
                >
                  <X size={15} />
                </button>
              </div>

              {/* Critical Bottleneck Alert Notice */}
              {selectedService.name === bottleneckService && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 space-y-1">
                  <div className="flex items-center space-x-1.5 font-bold text-rose-400 text-xs">
                    <Flame size={14} className="animate-pulse" />
                    <span>Primary System Bottleneck</span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-rose-300/90">
                    Identified by DPBPS bottleneck detection as the root constraint under current traffic. Priority scaling allocations will concentrate on this microservice.
                  </p>
                </div>
              )}

              {/* Live Telemetry Quad Grid */}
              <div className="grid grid-cols-2 gap-2.5 font-mono">
                <div className="p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">REPLICAS (READY/DES)</span>
                  <span className="text-sm font-bold text-cyan-400 mt-0.5 block">
                    {selectedService.ready_replicas} / {selectedService.desired_replicas ?? selectedService.ready_replicas}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">THROUGHPUT</span>
                  <span className="text-sm font-bold text-text-primary mt-0.5 block">
                    {(selectedService.request_rate ?? 0).toFixed(1)} <span className="text-[10px] text-text-muted font-normal font-sans">req/s</span>
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">P95 LATENCY</span>
                  <span className={`text-sm font-bold mt-0.5 block ${(selectedService.p95_latency ?? 0) > 200 ? "text-rose-400" : "text-text-primary"}`}>
                    {(selectedService.p95_latency ?? 0).toFixed(1)} <span className="text-[10px] text-text-muted font-normal font-sans">ms</span>
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">CPU UTILIZATION</span>
                  <span className={`text-sm font-bold mt-0.5 block ${((selectedService.cpu_utilisation ?? 0) >= 0.7) ? "text-rose-400" : "text-text-primary"}`}>
                    {((selectedService.cpu_utilisation ?? 0) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">MEMORY UTIL.</span>
                  <span className="text-sm font-bold text-blue-400 mt-0.5 block">
                    {((selectedService.memory_utilisation ?? 0) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-canvas-dark border border-canvas-border">
                  <span className="text-text-muted text-[10px] block font-sans">ERROR RATE</span>
                  <span className="text-sm font-bold text-text-muted mt-0.5 block">
                    {((selectedService.error_rate ?? 0) * 100).toFixed(2)}%
                  </span>
                </div>
              </div>

              {/* Call Graph: Incoming Callers */}
              <div className="bg-canvas-dark border border-canvas-border rounded-lg p-3 space-y-2">
                <span className="text-text-muted text-[11px] font-semibold flex items-center space-x-1">
                  <ArrowDownRight size={13} className="text-amber-400" />
                  <span>Incoming Callers ({incomingMap[selectedService.name]?.length ?? 0}):</span>
                </span>
                {incomingMap[selectedService.name] && incomingMap[selectedService.name].length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {incomingMap[selectedService.name].map((caller) => (
                      <button
                        key={caller}
                        onClick={() => {
                          const target = serviceMap.get(caller);
                          if (target) setSelectedService(target);
                        }}
                        className="px-2 py-0.5 rounded bg-canvas-card hover:bg-canvas-hover border border-canvas-border text-amber-300 font-mono text-[10px] transition-colors"
                        title="Click to inspect caller"
                      >
                        {caller}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span className="text-text-muted text-[11px] italic block">Ingress root (receives external traffic)</span>
                )}
              </div>

              {/* Call Graph: Outgoing Dependencies */}
              <div className="bg-canvas-dark border border-canvas-border rounded-lg p-3 space-y-2">
                <span className="text-text-muted text-[11px] font-semibold flex items-center space-x-1">
                  <ArrowRight size={13} className="text-cyan-400" />
                  <span>Outgoing Downstream Services ({selectedService.dependencies?.length ?? 0}):</span>
                </span>
                {selectedService.dependencies && selectedService.dependencies.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedService.dependencies.map((dep) => (
                      <button
                        key={dep}
                        onClick={() => {
                          const target = serviceMap.get(dep);
                          if (target) setSelectedService(target);
                        }}
                        className="px-2 py-0.5 rounded bg-canvas-card hover:bg-canvas-hover border border-canvas-border text-cyan-400 font-mono text-[10px] transition-colors"
                        title="Click to inspect downstream dependency"
                      >
                        {dep}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span className="text-text-muted text-[11px] italic block">Leaf service (no downstream calls)</span>
                )}
              </div>

              {/* Latest DPBPS Decision Card */}
              {decisionMap.get(selectedService.name) && (
                <div className="bg-canvas-dark border border-canvas-border rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
                      DPBPS Scaling Recommendation
                    </span>
                    <StatusBadge
                      status={decisionMap.get(selectedService.name)!.dpbps_decision}
                      variant={
                        decisionMap.get(selectedService.name)!.dpbps_decision === "SCALE_UP"
                          ? "rose"
                          : decisionMap.get(selectedService.name)!.dpbps_decision === "SCALE_DOWN"
                          ? "amber"
                          : "emerald"
                      }
                      size="xs"
                    />
                  </div>
                  <div className="text-[11px] font-mono text-text-secondary">
                    Target: <span className="text-cyan-400 font-bold">{decisionMap.get(selectedService.name)!.current_replicas} &rarr; {decisionMap.get(selectedService.name)!.proposed_replica_count} Pods</span>
                  </div>
                  <p className="text-[11px] text-text-secondary leading-relaxed">
                    {decisionMap.get(selectedService.name)!.reason}
                  </p>
                </div>
              )}

              {/* Navigation Actions */}
              <div className="pt-2 flex items-center justify-between text-xs border-t border-canvas-border">
                <Link
                  to="/services"
                  className="text-cyan-400 hover:text-cyan-300 font-medium flex items-center space-x-1"
                >
                  <span>Inventory Details</span>
                  <ArrowRight size={12} />
                </Link>
                <Link
                  to="/bottlenecks"
                  className="text-rose-400 hover:text-rose-300 font-medium flex items-center space-x-1"
                >
                  <span>Bottleneck Analysis</span>
                  <ArrowRight size={12} />
                </Link>
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-text-muted text-xs space-y-2">
              <Network size={28} className="mx-auto text-text-muted opacity-40 mb-1" />
              <p className="font-medium text-text-secondary">No Service Selected</p>
              <p className="leading-relaxed">
                Click any microservice node in the DAG canvas to inspect real-time CPU/memory utilization, replica counts, incoming callers, and DPBPS scaling recommendations.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
