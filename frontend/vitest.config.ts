import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "jsdom", css: { include: [/theme\.css/] }, setupFiles: ["./src/test-setup.ts"], include: ["src/**/*.test.tsx", "src/**/*.test.ts"] } });
