import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
// M2O_API_PROXY=http://localhost:8080 serves this hot-reloading frontend against the running
// Compose stack, presenting that stack's own origin so its origin and host checks accept it.
const stack = process.env.M2O_API_PROXY;
export default defineConfig({
  // Utilities only (see src/utilities.css): the command menu and the signature moment's views use them.
  plugins: [tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": stack
        ? { target: stack, changeOrigin: true, headers: { origin: stack } }
        : "http://127.0.0.1:8000",
    },
  },
});
