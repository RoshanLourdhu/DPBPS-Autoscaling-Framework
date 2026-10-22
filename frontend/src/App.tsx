import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import OverviewDashboard from "./pages/OverviewDashboard";
import EnvironmentsPage from "./pages/EnvironmentsPage";
import WorkloadsPage from "./pages/WorkloadsPage";
import ServicesPage from "./pages/ServicesPage";
import ScalingPage from "./pages/ScalingPage";
import DeploymentsPage from "./pages/DeploymentsPage";
import ExperimentsPage from "./pages/ExperimentsPage";
import SettingsPage from "./pages/SettingsPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<OverviewDashboard />} />
          <Route path="environments" element={<EnvironmentsPage />} />
          <Route path="workloads" element={<WorkloadsPage />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="scaling" element={<ScalingPage />} />
          <Route path="deployments" element={<DeploymentsPage />} />
          <Route path="experiments" element={<ExperimentsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
