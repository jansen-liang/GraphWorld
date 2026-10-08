import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const allowedHosts = [".cpolar.io", ".cpolar.cn", ".cpolar.top"];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const proxy = { "/api": env.GRAPHWORLD_API_URL ?? "http://127.0.0.1:8010" };
  return {
    root: "web",
    plugins: [react()],
    build: { outDir: "../dist" },
    // This workspace is commonly opened together with VS Code/Pylance and
    // several backend watchers. Polling keeps Vite from exhausting the
    // user's shared inotify watcher quota and crashing with ENOSPC.
    server: {
      allowedHosts,
      proxy,
      watch: { usePolling: true, interval: 1000 },
    },
    preview: { allowedHosts, proxy },
  };
});
