import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Shell } from "../components/layout/Shell";
import { LoginPage } from "../features/auth/LoginPage";
import { SceneListPage } from "../features/scene-browser/SceneListPage";
import { SceneDetailPage } from "../features/scene-browser/SceneDetailPage";
import { RunConfigPage } from "../features/run-config/RunConfigPage";
import { RunDetailPage } from "../features/run-monitor/RunDetailPage";
import { RunListPage } from "../features/run-monitor/RunListPage";
import { ReplayPage } from "../features/replay/ReplayPage";
import { SceneBuilderPage } from "../features/scene-builder/SceneBuilderPage";

export function App() {
  const auth = useAuth();
  if (auth.isLoading) {
    return <div className="loading-screen">Loading session.</div>;
  }
  if (!auth.user) {
    return <LoginPage />;
  }
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/scenes" replace />} />
          <Route path="/scenes" element={<SceneListPage />} />
          <Route path="/scenes/:sceneId" element={<SceneDetailPage />} />
          <Route path="/scenes/:sceneId/edit" element={<SceneBuilderPage />} />
          <Route path="/runs" element={<RunListPage />} />
          <Route path="/runs/new" element={<RunConfigPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/runs/:runId/replay" element={<ReplayPage />} />
          <Route path="*" element={<Navigate to="/scenes" replace />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
