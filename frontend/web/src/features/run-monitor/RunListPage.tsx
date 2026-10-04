import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../../app/auth";
import { listRuns } from "../../api/runs";

export function RunListPage() {
  const auth = useAuth();
  const runs = useQuery({ queryKey: ["runs"], queryFn: listRuns });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">{auth.isAdmin ? "All Users" : "My Data"}</p>
          <h1>Runs</h1>
        </div>
      </header>

      <div className="table-list">
        {runs.data?.map((run) => (
          <Link className="table-row run-row" key={run.id} to={`/runs/${run.id}`}>
            <Activity size={16} aria-hidden />
            <div>
              <strong>{run.id}</strong>
              <small>
                {run.scene_version_id} · {run.control_mode} · {run.visibility_mode}
                {auth.isAdmin && ` · owner ${run.owner_username ?? run.owner_user_id ?? "unknown"}`}
              </small>
            </div>
            <div className="run-row-meta">
              <span className={`status-pill ${run.status}`}>{run.status}</span>
              <span>step {run.current_step}</span>
            </div>
            <ChevronRight size={16} aria-hidden />
          </Link>
        ))}
        {!runs.isLoading && !runs.data?.length && <div className="empty-panel">No runs yet.</div>}
      </div>
    </section>
  );
}
