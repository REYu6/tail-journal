import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "PET_DEV_");
  const backend = env.PET_DEV_API_URL || "http://127.0.0.1:8000";
  const proxy = { target: backend, changeOrigin: false };
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: { "/api": proxy, "/r/": proxy },
    },
  };
});
