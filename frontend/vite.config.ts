import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
export default defineConfig({
  // Utilities only (see src/utilities.css): the command menu and the signature moment's views use them.
  plugins: [tailwindcss()],
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
