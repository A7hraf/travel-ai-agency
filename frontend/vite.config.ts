import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Shown on the login page, so anyone can tell at a glance which version the site runs.
  define: { __BUILD_TIME__: JSON.stringify(new Date().toISOString()) },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
