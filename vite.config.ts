import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

const backendProxyTarget = process.env.VITE_BACKEND_PROXY_TARGET || "http://127.0.0.1:8000";
const apiProxy = {
  "/api": {
    target: backendProxyTarget,
    changeOrigin: false,
    ws: true,
  },
};

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    proxy: apiProxy,
    hmr: {
      overlay: false,
    },
  },
  preview: {
    host: "::",
    port: 8080,
    proxy: apiProxy,
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query"],
  },
}));
