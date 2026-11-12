// src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import OverviewDashboard from "./pages/OverviewDashboard";
import ServicesPage from "./pages/ServicesPage";
import ServiceTopologyPage from "./pages/ServiceTopologyPage";
import BottleneckAnalysisPage from "./pages/BottleneckAnalysisPage";
import DpbpsIntelligencePage from "./pages/DpbpsIntelligencePage";
import DeploymentsPage from "./pages/DeploymentsPage";
import ExperimentsPage from "./pages/ExperimentsPage";
import PerformanceAnalyticsPage from "./pages/PerformanceAnalyticsPage";
import ScalingPage from "./pages/ScalingPage";
import SettingsPage from "./pages/SettingsPage";
import EnvironmentsPage from "./pages/EnvironmentsPage";
import WorkloadsPage from "./pages/WorkloadsPage";

function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<OverviewDashboard />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="topology" element={<ServiceTopologyPage />} />
          <Route path="bottlenecks" element={<BottleneckAnalysisPage />} />
          <Route path="intelligence" element={<DpbpsIntelligencePage />} />
          <Route path="deployments" element={<DeploymentsPage />} />
          <Route path="experiments" element={<ExperimentsPage />} />
          <Route path="analytics" element={<PerformanceAnalyticsPage />} />
          <Route path="scaling" element={<ScalingPage />} />
          <Route path="settings" element={<SettingsPage />} />
          {/* Legacy routes preserved for backwards compatibility */}
          <Route path="environments" element={<EnvironmentsPage />} />
          <Route path="workloads" element={<WorkloadsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
