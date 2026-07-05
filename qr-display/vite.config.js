import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const backendTarget = process.env.VITE_BACKEND_API_BASE || "http://127.0.0.1:4300";
const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    host: true,
    port: Number(process.env.VITE_QR_PORT || 5173),
    proxy: {
      "/internal": {
        target: backendTarget,
        changeOrigin: true,
      },
      "/v1": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(rootDir, "index.html"),
        qr: resolve(rootDir, "qr.html"),
      },
    },
  },
});
