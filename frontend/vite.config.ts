import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In docker-compose the dev server runs inside the frontend container, where
// `localhost` is NOT the backend. Point the proxy at the backend service via
// VITE_PROXY_TARGET (set to http://backend:8000 in docker-compose); fall back
// to localhost for plain local development.
const target = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/tracks": target,
      "/simulate": target,
      "/optimize": target,
      "/ocp": target,
      "/transient": target,
      "/sweep": target,
      "/health": target,
    },
  },
});
