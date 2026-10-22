// src/components/layout/TopNav.tsx
import { useEffect, useState } from "react";
import { CheckCircle, XCircle, HelpCircle } from "lucide-react";
import { fetchHealth } from "../../services/api";

export function TopNav() {
  const [backendStatus, setBackendStatus] = useState<string>("UNKNOWN");

  useEffect(() => {
    const check = async () => {
      try {
        const data = await fetchHealth();
        setBackendStatus(data.status === "ok" ? "CONNECTED" : "ERROR");
      } catch (_) {
        setBackendStatus("DISCONNECTED");
      }
    };
    check();
  }, []);

  const statusIcon =
    backendStatus === "CONNECTED" ? (
      <CheckCircle className="text-green-500" size={20} />
    ) : backendStatus === "DISCONNECTED" ? (
      <XCircle className="text-red-500" size={20} />
    ) : (
      <HelpCircle className="text-gray-400" size={20} />
    );

  return (
    <header className="bg-charcoal text-text flex items-center justify-between px-6 py-3 shadow-md">
      <h1 className="text-xl font-semibold text-accent-blue">DPBPS Platform</h1>
      <div className="flex items-center gap-2">
        <span className="text-sm">Backend:</span>
        {statusIcon}
        <span className="text-sm capitalize">{backendStatus.toLowerCase()}</span>
      </div>
    </header>
  );
}
