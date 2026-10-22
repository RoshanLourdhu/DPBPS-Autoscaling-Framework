// src/pages/EnvironmentsPage.tsx
import { useEffect, useState } from "react";
import type { EnvironmentInfo } from "../services/api";
import { fetchEnvironments } from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import { EnvironmentCard } from "../components/ui/EnvironmentCard";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { EmptyState } from "../components/ui/EmptyState";

export default function EnvironmentsPage() {
  const [envs, setEnvs] = useState<EnvironmentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEnvironments()
      .then(setEnvs)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  if (envs.length === 0) return <EmptyState message="No environments configured" />;

  return (
    <div className="p-6 space-y-4">
      <PageHeader title="Environments" subtitle="Configured simulation and real environments" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {envs.map((e) => (
          <EnvironmentCard
            key={e.id}
            name={e.name}
            description={e.description}
            status={e.status}
            demo={e.status === "DISCONNECTED" && !e.description}
          />
        ))}
      </div>
    </div>
  );
}
