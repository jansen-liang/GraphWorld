import { Check, MousePointerClick } from "lucide-react";
import { useState } from "react";
import type { CandidateAction } from "../../types/api";

interface CandidateActionPanelProps {
  actions: CandidateAction[];
  disabled?: boolean;
  onSelect: (action: CandidateAction, payload?: Record<string, unknown>) => void;
}

export function CandidateActionPanel({ actions, disabled = false, onSelect }: CandidateActionPanelProps) {
  const [anchors, setAnchors] = useState<Record<string, number[]>>({});
  if (!actions.length) {
    return <div className="empty-panel">No candidate actions.</div>;
  }

  return (
    <div className="action-list">
      {actions.map((action) => (
        <div key={action.action_id} className="action-entry">
          <button
            type="button"
            className="action-row"
            disabled={disabled || !action.legal || action.action_type === "place" || action.action_type === "release"}
            title={action.action_contract.description || action.preview || action.reason}
            onClick={() => onSelect(action)}
          >
            <MousePointerClick size={16} aria-hidden />
            <span className="action-main">
              <strong>{action.action_type}</strong>
              <span>
                {action.target_id || action.object_id || action.reason}
                {typeof action.payload.destination_room === "string" ? ` -> ${action.payload.destination_room}` : ""}
                {action.action_type === "dispense" && action.target_id ? " (new instance)" : ""}
                {action.action_type === "place" ? ` (${action.payload.placement_hint === "volume" ? "inside" : "surface"})` : ""}
                {action.action_type === "release" ? " (floor)" : ""}
                {action.action_contract.category ? ` · ${action.action_contract.category}` : ""}
              </span>
            </span>
          </button>
          {(action.action_type === "place" || action.action_type === "release") && action.legal && (() => {
            const isVolume = action.payload.placement_hint === "volume";
            const labels = action.action_type === "release" ? ["X", "Z"] : isVolume ? ["U", "V", "W"] : ["U", "V"];
            const values = anchors[action.action_id] ?? labels.map(() => 0.5);
            return <div className="action-geometry" aria-label="Placement anchor">
              {labels.map((label, index) => <label key={label}><span>{label}</span><input type="range" min="0" max="1" step="0.05" value={values[index] ?? 0.5} onChange={(event) => {
                const next = [...values]; next[index] = Number(event.target.value);
                setAnchors((current) => ({ ...current, [action.action_id]: next }));
              }} /><output>{(values[index] ?? 0.5).toFixed(2)}</output></label>)}
              <button type="button" className="icon-button" title="Apply anchor" aria-label="Apply anchor" disabled={disabled} onClick={() => {
                if (action.action_type === "release") onSelect(action, { release_anchor: [values[0] ?? 0.5, 0, values[1] ?? 0.5] });
                else if (isVolume) onSelect(action, { volume_anchor: values });
                else onSelect(action, { surface_anchor: values });
              }}><Check size={15} aria-hidden /></button>
            </div>;
          })()}
        </div>
      ))}
    </div>
  );
}
