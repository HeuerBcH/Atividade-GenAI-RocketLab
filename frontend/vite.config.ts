import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: { chunkSizeWarningLimit: 800 }, // o recharts sozinho já passa dos 500 kB
});
