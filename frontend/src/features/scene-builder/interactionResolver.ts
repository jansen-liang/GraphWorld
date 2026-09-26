export type CanonicalInteraction = "open" | "close" | "press" | "pick" | "place" | "drain";

export interface LocalInteractionTarget {
  id: string;
  capabilities: string[];
  componentRole?: string;
  isOpen?: boolean;
  hostRunning?: boolean;
  startRequiresClosed?: boolean;
  accessOpen?: boolean;
  pickable?: boolean;
  placeTarget?: boolean;
}

export interface LocalInteractionResolution {
  action: CanonicalInteraction | null;
  failure?: string;
}

/**
 * Resolve editor-preview input into the same canonical action vocabulary as
 * the backend runtime. Three.js remains responsible only for hit testing and
 * visual projection; capabilities and state decide the semantic result.
 */
export function resolveLocalInteraction(
  target: LocalInteractionTarget,
  heldObjectId: string | null,
): LocalInteractionResolution {
  const capabilities = new Set(target.capabilities.map((value) => value.toLowerCase()));
  const role = (target.componentRole ?? "").toLowerCase();
  if (capabilities.has("drainable") || role === "sink_drain") return { action: "drain" };

  if (heldObjectId) {
    if (target.placeTarget || capabilities.has("place_target") || capabilities.has("receptacle") || capabilities.has("support_surface")) {
      return { action: "place" };
    }
    return { action: null, failure: `target cannot receive held object: ${target.id}` };
  }

  const openable = capabilities.has("openable") || role === "door" || role.startsWith("drawer");
  if (openable) {
    if (target.hostRunning) return { action: null, failure: `device is running; access is locked: ${target.id}` };
    return { action: target.isOpen ? "close" : "open" };
  }
  if (capabilities.has("switchable") || capabilities.has("water_source_control") || role.includes("button") || role.includes("knob")) {
    if (target.hostRunning) return { action: null, failure: `device is already running: ${target.id}` };
    if (target.startRequiresClosed && target.accessOpen) {
      return { action: null, failure: `device access must be closed before start: ${target.id}` };
    }
    return { action: "press" };
  }
  if (target.pickable || capabilities.has("pickable") || capabilities.has("pickupable") || capabilities.has("graspable")) {
    return { action: "pick" };
  }
  return { action: null, failure: `no affordance for interaction: ${target.id}` };
}
