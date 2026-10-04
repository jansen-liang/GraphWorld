import { create } from "zustand";

interface SceneViewState {
  selectedNodeId: string;
  setSelectedNodeId: (nodeId: string) => void;
}

export const useSceneViewStore = create<SceneViewState>((set) => ({
  selectedNodeId: "",
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId }),
}));
