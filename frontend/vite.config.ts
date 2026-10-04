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
    server: { allowedHosts, proxy },
    preview: { allowedHosts, proxy },
  };
});
