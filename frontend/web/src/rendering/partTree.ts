/**
 * Three.js-side articulation adapter. The backend PartTree remains the
 * semantic source of truth; this module only exposes the runtime link/joint
 * operations needed to build and animate its visual tree.
 */
export {
  attachHinge,
  attachLocalPart,
  attachPart,
  attachPrismatic,
  applyRuntimeJointState,
  createComposite,
  updateComposites,
} from "../features/scene-builder/compositeRuntime";
export type { CompositeObject, CompositePart, CompositeJoint, JointKind } from "../features/scene-builder/compositeRuntime";
