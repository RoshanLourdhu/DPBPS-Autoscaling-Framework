// src/components/layout/Sidebar.tsx
import { NavLink } from "react-router-dom";
import { LayoutDashboard, Server, Cpu, Settings, BarChart2, Boxes, FileStack, Rocket } from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/environments", label: "Environments", icon: Server },
  { to: "/workloads", label: "Workloads", icon: Cpu },
  { to: "/services", label: "Services", icon: Boxes },
  { to: "/scaling", label: "Scaling", icon: BarChart2 },
  { to: "/deployments", label: "Deployments", icon: Rocket },
  { to: "/experiments", label: "Experiments", icon: FileStack },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="bg-charcoal text-text h-full w-64 flex flex-col p-4 overflow-y-auto">
      <h1 className="text-2xl font-bold mb-6 text-accent-blue">DPBPS</h1>
      <nav className="flex flex-col gap-2">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            className={({ isActive }) =>
              `flex items-center gap-3 p-2 rounded transition-colors ${
                isActive ? "bg-accent-blue bg-opacity-20 text-accentBlue" : "hover:bg-accentBlue hover:bg-opacity-10"
              }`
            }
          >
            <Icon size={20} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
