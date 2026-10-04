import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Database } from "lucide-react";
import { Link } from "react-router-dom";
import { listScenes } from "../../api/scenes";

export function SceneListPage() {
  const scenes = useQuery({ queryKey: ["scenes"], queryFn: listScenes });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Scene Registry</p>
          <h1>Scenes</h1>
        </div>
        <Link className="button primary" to="/runs/new">
          New Run
          <ArrowRight size={16} aria-hidden />
        </Link>
      </header>

      {scenes.isLoading && <div className="empty-panel">Loading scenes.</div>}
      {scenes.error && <div className="error-panel">{scenes.error.message}</div>}
      {scenes.data && !scenes.data.length && <div className="empty-panel">No scenes imported.</div>}

      <div className="table-list">
        {scenes.data?.map((scene) => (
          <Link key={scene.id} className="table-row" to={`/scenes/${scene.id}`}>
            <Database size={18} aria-hidden />
            <span>
              <strong>{scene.name || scene.id}</strong>
              <small>{scene.domain || "domain"} · {scene.id}</small>
            </span>
            <ArrowRight size={18} aria-hidden />
          </Link>
        ))}
      </div>
    </section>
  );
}
