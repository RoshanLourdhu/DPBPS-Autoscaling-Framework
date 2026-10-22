// src/components/layout/AppLayout.tsx
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";

export function AppLayout() {
  return (
    <div className="flex h-screen bg-navy text-text">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopNav />
        <main className="flex-1 overflow-y-auto p-6 bg-charcoal">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
