import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function allowedHostsFromEnv(env) {
  const hosts = new Set();

  for (const origin of (env.CORS_ORIGINS || "").split(",")) {
    const value = origin.trim();
    if (!value) continue;
    try {
      hosts.add(new URL(value).hostname);
    } catch {
      // Ignore malformed origins here; FastAPI validates CORS separately.
    }
  }

  for (const host of (env.VITE_ALLOWED_HOSTS || "").split(",")) {
    const value = host.trim();
    if (value) hosts.add(value);
  }

  return [...hosts];
}

export default defineConfig(({ mode }) => {
  // envDir points Vite at the project-root .env instead of frontend/.env.
  const env = loadEnv(mode, "..", ["CORS_ORIGINS", "VITE_ALLOWED_HOSTS"]);

  return {
    plugins: [react()],
    server: {
      allowedHosts: allowedHostsFromEnv(env),
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, "")
        }
      }
    }
  };
});
