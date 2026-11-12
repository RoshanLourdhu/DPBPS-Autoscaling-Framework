// src/components/layout/Sidebar.tsx
import React, { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Boxes,
  Network,
  Flame,
  Brain,
  Rocket,
  FlaskConical,
  BarChart3,
  History,
  Sliders,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Activity,
  X,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  badge?: string;
}

const navItems: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/services", label: "Service Monitoring", icon: Boxes },
  { to: "/topology", label: "Service Topology", icon: Network },
  { to: "/bottlenecks", label: "Bottleneck Analysis", icon: Flame },
  { to: "/intelligence", label: "DPBPS Intelligence", icon: Brain },
  { to: "/deployments", label: "Deployment Intelligence", icon: Rocket },
  { to: "/experiments", label: "Experiments", icon: FlaskConical },
  { to: "/analytics", label: "Performance Analytics", icon: BarChart3 },
  { to: "/scaling", label: "Scaling History", icon: History },
  { to: "/settings", label: "System Configuration", icon: Sliders },
];

export interface SidebarProps {
  isMobileOpen?: boolean;
  onMobileClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isMobileOpen = false, onMobileClose }) => {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem("dpbps_sidebar_collapsed");
      return saved ? JSON.parse(saved) : false;
    } catch {
      return false;
    }
  });

  const location = useLocation();

  useEffect(() => {
    try {
      localStorage.setItem("dpbps_sidebar_collapsed", JSON.stringify(isCollapsed));
    } catch {}
  }, [isCollapsed]);

  // Close mobile drawer on route change
  useEffect(() => {
    if (onMobileClose) {
      onMobileClose();
    }
  }, [location.pathname, onMobileClose]);

  return (
    <>
      {/* Mobile Drawer Backdrop */}
      {isMobileOpen && (
        <div
          onClick={onMobileClose}
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden transition-opacity"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`bg-canvas-card border-r border-canvas-border flex flex-col transition-all duration-300 ease-in-out z-50 lg:z-auto ${
          // Mobile: fixed drawer
          isMobileOpen
            ? "fixed inset-y-0 left-0 w-64 shadow-2xl flex"
            : "fixed -translate-x-full lg:translate-x-0 lg:static"
        } ${
          // Desktop: sticky in-flow sidebar
          isCollapsed ? "lg:w-16" : "lg:w-64"
        } h-screen flex-shrink-0 sticky top-0`}
      >
        {/* Header / Brand Identity */}
        <div className="h-14 border-b border-canvas-border flex items-center justify-between px-3.5 flex-shrink-0">
          <div className="flex items-center space-x-2.5 overflow-hidden">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white shadow-glow flex-shrink-0">
              <Activity size={18} className="animate-pulse" />
            </div>
            {(!isCollapsed || isMobileOpen) && (
              <div className="flex flex-col min-w-0">
                <span className="font-bold text-sm tracking-wider text-text-primary uppercase flex items-center space-x-1.5 truncate">
                  <span>DPBPS</span>
                  <span className="text-[10px] font-semibold px-1 py-0.2 rounded bg-cyan-500/20 text-cyan-400">
                    CORE
                  </span>
                </span>
                <span className="text-[10px] text-text-muted font-mono truncate">
                  Autonomous Scaling
                </span>
              </div>
            )}
          </div>

          {/* Desktop collapse toggle */}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-canvas-hover transition-colors hidden lg:flex"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
          </button>

          {/* Mobile close toggle */}
          <button
            onClick={onMobileClose}
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-canvas-hover transition-colors lg:hidden"
            title="Close menu"
          >
            <X size={16} />
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 overflow-y-auto p-2.5 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.to === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(item.to);

            const showCollapsedView = isCollapsed && !isMobileOpen;

            return (
              <div key={item.to} className="relative group">
                <NavLink
                  to={item.to}
                  className={`flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150 ${
                    isActive
                      ? "bg-cyan-500/10 text-cyan-400 border-l-2 border-cyan-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
                      : "text-text-secondary hover:text-text-primary hover:bg-canvas-hover"
                  } ${showCollapsedView ? "justify-center px-0" : ""}`}
                >
                  <Icon
                    size={17}
                    className={`flex-shrink-0 ${
                      isActive ? "text-cyan-400" : "text-text-muted group-hover:text-text-primary"
                    }`}
                  />
                  {!showCollapsedView && (
                    <span className="truncate flex-1">{item.label}</span>
                  )}
                  {!showCollapsedView && item.badge && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-canvas-dark text-cyan-400">
                      {item.badge}
                    </span>
                  )}
                </NavLink>

                {/* Collapsed Tooltip */}
                {showCollapsedView && (
                  <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2.5 py-1 bg-canvas-elevated border border-canvas-border text-text-primary text-xs rounded-md shadow-card pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50 whitespace-nowrap">
                    {item.label}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Footer / Operating Posture Badge */}
        <div className="p-3 border-t border-canvas-border flex-shrink-0 bg-canvas-dark/40">
          {!isCollapsed || isMobileOpen ? (
            <div className="p-2.5 rounded-lg bg-canvas-elevated border border-canvas-border text-xs space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider flex items-center space-x-1">
                  <ShieldCheck size={13} className="text-amber-400" />
                  <span>Mode</span>
                </span>
                <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">
                  DRY_RUN
                </span>
              </div>
              <div className="text-[10px] text-text-muted leading-tight">
                Kubernetes actuation is dry-run verified. Mutations inhibited.
              </div>
            </div>
          ) : (
            <div className="flex justify-center" title="Operating Mode: DRY_RUN Active">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400 ring-4 ring-amber-400/20 animate-pulse" />
            </div>
          )}
        </div>
      </aside>
    </>
  );
};
