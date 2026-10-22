// One command for the visual check: start a throwaway demo-mode stack built from this
// checkout, compare the screenshots against it, then remove the stack and its data.
// Usage (from frontend, in any shell): npm run test:visual:demo, :demo:update or :demo:keep
//   :update  rewrite the baselines instead of comparing
//   :keep    leave the stack running afterwards (remove it with the command it prints)
// It runs beside a private stack on 8080 without touching it: its own Compose project,
// ports and database volume, and every provider credential blanked so none loads.
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontend, "..");
const port = 8090;
const project = ["compose", "-p", "m2o-visual"];
const blank = [
  "MTT_GITHUB_TOKEN",
  "GITHUB_ALLOWED_REPOS",
  "JIRA_CLIENT_ID",
  "JIRA_CLIENT_SECRET",
  "SLACK_CLIENT_ID",
  "SLACK_CLIENT_SECRET",
  "SLACK_APP_ID",
  "SLACK_SIGNING_SECRET",
  "LINKEDIN_CLIENT_ID",
  "LINKEDIN_CLIENT_SECRET",
  "PROVIDER_ENCRYPTION_KEY",
  "GOOGLE_MEET_CLIENT_ID",
  "GOOGLE_MEET_CLIENT_SECRET",
];
// Shell values take precedence over the root .env in Compose, so an empty value here
// keeps a private credential out of the demo stack.
const env = {
  ...process.env,
  ...Object.fromEntries(blank.map((name) => [name, ""])),
  APP_PORT: String(port),
  POSTGRES_PORT: "55433",
  PUBLIC_DEMO_MODE: "true",
  LINKEDIN_PUBLISHING_ENABLED: "false",
  VISITOR_START_LIMIT: "50",
};
const update = process.argv.includes("--update"),
  keep = process.argv.includes("--keep");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: "inherit", cwd: root, env, ...options });
  if (result.error) throw new Error(`Could not run ${command}: ${result.error.message}`);
  return result.status ?? 1;
}

async function ready() {
  for (let attempt = 0; attempt < 90; attempt++) {
    try {
      if ((await fetch(`http://localhost:${port}/`)).ok) return true;
    } catch {
      /* Not listening yet. */
    }
    await new Promise((done) => setTimeout(done, 2000));
  }
  return false;
}

let status = 1;
try {
  console.log(`Starting the throwaway demo stack on port ${port}…`);
  if (run("docker", [...project, "up", "-d", "--build", "web", "worker"]) !== 0)
    throw new Error("The demo stack did not start. Is Docker Desktop running?");
  if (!(await ready())) throw new Error(`The demo stack did not answer on port ${port} within 3 minutes.`);
  status = run(process.execPath, ["scripts/visual-docker.mjs", ...(update ? ["--update"] : [])], {
    cwd: frontend,
    env: { ...env, MTT_VISUAL_HOST_PORT: String(port) },
  });
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
} finally {
  if (keep) console.log(`Left running. Remove it with: docker compose -p m2o-visual down -v`);
  else {
    console.log("Removing the throwaway demo stack…");
    run("docker", [...project, "down", "-v"]);
  }
}
console.log(status === 0 ? "Visual check passed." : "Visual check failed; see the output above.");
process.exit(status);
