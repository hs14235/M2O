// Run the visual spec inside the official Playwright Linux image so screenshots match CI.
// Usage: node scripts/visual-docker.mjs [--update]  (expects the Compose stack on port 8080)
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
// The image's browsers must match the installed test runner exactly.
const { version } = JSON.parse(
  readFileSync(resolve(frontend, "node_modules/@playwright/test/package.json"), "utf8"),
);
const test = `npx playwright test e2e/visual.spec.ts${process.argv.includes("--update") ? " --update-snapshots" : ""}`;
const linux = process.platform === "linux";
// The API only trusts the localhost Host header. On Linux the container shares the host
// network, so localhost:8080 is the Compose stack. Docker Desktop has no host network, so a
// TCP relay inside the container carries localhost:8080 to host.docker.internal, and the
// tests start only once the relay is listening.
const relay =
  "const net = require('net'); net.createServer((c) => { const u = net.connect(8080, 'host.docker.internal');" +
  " c.pipe(u).pipe(c); c.on('error', () => u.destroy()); u.on('error', () => c.destroy()); })" +
  `.listen(8080, '127.0.0.1', () => { require('child_process').spawn('bash', ['-c', '${test}'], { stdio: 'inherit' })` +
  ".on('exit', (code) => process.exit(code ?? 1)); });";
const args = [
  "run", "--rm", "--ipc=host",
  ...(linux
    ? ["--network=host", "--user", `${process.getuid()}:${process.getgid()}`, "-e", "HOME=/tmp"]
    : ["--add-host=host.docker.internal:host-gateway"]),
  "-v", `${frontend}:/work`, "-w", "/work",
  "-e", "MTT_E2E_URL=http://localhost:8080", "-e", "MTT_VISUAL=1",
  `mcr.microsoft.com/playwright:v${version}-noble`,
  ...(linux ? ["bash", "-c", test] : ["node", "-e", relay]),
];
const result = spawnSync("docker", args, { stdio: "inherit" });
if (result.error) console.error(`Could not run docker: ${result.error.message}`);
process.exit(result.status ?? 1);
