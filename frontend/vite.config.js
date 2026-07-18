import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy /api/* calls to FastAPI backend at :8000
      "/api": {
        target:      "http://localhost:8000",
        changeOrigin: true,
        secure:       false,
      },
      "/healthz": {
        target:       "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
