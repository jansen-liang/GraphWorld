import { useQuery } from "@tanstack/react-query";
import { Activity, GitBranch, ListChecks, PlusCircle, RotateCw } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../../app/auth";
import { getRunCurrent } from "../../api/runs";

const navItems = [
  { to: "/scenes", label: "Scenes", icon: GitBranch },
  { to: "/runs", label: "Runs", icon: ListChecks },
  { to: "/runs/new", label: "New Run", icon: PlusCircle },
];

export function Shell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  const runId = location.pathname.match(/^\/runs\/([^/]+)/)?.[1] ?? "";
  const isRunPage = Boolean(runId && runId !== "new");
  const currentRun = useQuery({
    queryKey: ["run-current", runId],
    queryFn: () => getRunCurrent(runId),
    enabled: isRunPage,
    refetchInterval: (query) => {
      const status = query.state.data?.run.status ?? "";
      return ["pending", "running", "waiting_for_human"].includes(status) ? 1800 : false;
    },
  });
  const metrics = currentRun.data?.metrics ?? {};
  const summaryItems = [
    { label: "Final", value: scoreValue(metrics.final_score) },
    { label: "State", value: scoreValue(metrics.state_score) },
    { label: "Spatial", value: scoreValue(metrics.spatial_score) },
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Activity size={22} aria-hidden />
          <span>GraphWorld</span>
        </div>
        <nav className="nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                <Icon size={18} aria-hidden />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
        <section className="sidebar-user">
          <span>{auth.isAdmin ? "Admin" : "User"}</span>
          <strong>{auth.user?.display_name || auth.user?.username}</strong>
          <button className="text-button" type="button" onClick={() => auth.logout()}>
            Sign out
          </button>
        </section>
        {isRunPage && (
          <section className="sidebar-run" aria-label="Current run summary">
            <div className="sidebar-run-heading">
              <span>Current Run</span>
              <RotateCw size={14} aria-hidden />
            </div>
            <strong title={runId}>{runId}</strong>
            <div className="sidebar-run-status">
              <span className={`status-pill ${currentRun.data?.run.status ?? ""}`}>
                {currentRun.data?.run.status ?? "loading"}
              </span>
              <span>step {currentRun.data?.run.current_step ?? 0}</span>
            </div>
            <dl className="sidebar-score-list">
              {summaryItems.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
            <div className="sidebar-latest">
              <span>Latest</span>
              <strong>{String(metrics.last_action_id ?? "No action yet")}</strong>
            </div>
          </section>
        )}
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

function scoreValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "--";
}
