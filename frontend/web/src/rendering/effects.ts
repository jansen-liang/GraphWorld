import * as THREE from "three";

export type VisualEffectKind = "droplet" | "drying" | "steam" | "broken" | "stain";

export interface VisualEffect {
  mesh: THREE.Mesh;
  host: THREE.Mesh;
  nodeId: string;
  kind: VisualEffectKind;
  offset: THREE.Vector3;
  phase: number;
}

type NodeLike = { states?: unknown; visual_cues?: unknown };

function statesOf(node: NodeLike | undefined): Record<string, unknown> {
  return node?.states && typeof node.states === "object" ? node.states as Record<string, unknown> : {};
}

export function visualCuesOf(node: NodeLike | undefined): ReadonlySet<string> {
  return new Set(
    Array.isArray(node?.visual_cues)
      ? node.visual_cues.filter((cue): cue is string => typeof cue === "string")
      : [],
  );
}

function visibleFor(kind: VisualEffectKind, states: Record<string, unknown>, cues: ReadonlySet<string>): boolean {
  if (kind === "droplet") return cues.has("water_droplets") || Boolean(states.is_wet);
  if (kind === "drying") return cues.has("drying_bubbles") || (Boolean(states.is_wet) && states.cycle_remaining != null);
  if (kind === "steam") return cues.has("steam") || String(states.temperature || "").toLowerCase() === "hot";
  if (kind === "stain") return cues.has("stain") || Boolean(states.is_dirty);
  return cues.has("broken") || Boolean(states.is_broken);
}

/** Apply purely visual state effects; backend state remains authoritative. */
export function updateVisualEffects(
  effects: readonly VisualEffect[],
  nodes: ReadonlyMap<string, NodeLike>,
  time: number,
): void {
  effects.forEach(({ mesh, host, nodeId, kind, offset, phase }) => {
    const node = nodes.get(nodeId);
    mesh.visible = visibleFor(kind, statesOf(node), visualCuesOf(node));
    if (!mesh.visible) return;
    mesh.position.copy(host.position).add(offset);
    if (kind === "droplet") {
      const slide = (time * 0.22 + phase * 0.17) % 1;
      const bounds = host.geometry.boundingBox;
      if (bounds) mesh.position.y = host.position.y + offset.y + bounds.min.y + slide * (bounds.max.y - bounds.min.y);
      mesh.position.x += Math.sin(time * 4 + phase) * 0.008;
      mesh.scale.setScalar(0.78 + 0.22 * Math.sin(time * 4 + phase) ** 2);
    } else if (kind === "drying" || kind === "steam") {
      mesh.position.y += (Math.sin(time * 3.5 + phase) + 1) * 0.025;
      mesh.scale.setScalar(0.72 + 0.28 * Math.sin(time * 2.5 + phase) ** 2);
    } else if (kind === "broken") {
      mesh.rotation.y = time * 0.12;
    }
  });
}
