import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: forwards /api/web/* to the WEB API folder (port 8001). The mobile API (8002) is never used here.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api/web": "http://localhost:8001" } },
});
