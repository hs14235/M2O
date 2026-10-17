import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
export default defineConfig({
  plugins: [tailwindcss()],
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  // The style guide is a second page with its own bundle, so the app never loads it.
  build: { rollupOptions: { input: { main: "index.html", styleguide: "styleguide.html" } } },
});
