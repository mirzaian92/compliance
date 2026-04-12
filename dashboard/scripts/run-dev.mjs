import { spawn } from "node:child_process";
import path from "node:path";

const NEXT_BIN = path.join(process.cwd(), "node_modules", "next", "dist", "bin", "next");
function runNode(scriptPath, args) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [scriptPath, ...args], {
      // Some locked-down Windows environments block spawning when stdio is piped.
      // Use inherited stdio for reliability.
      stdio: "inherit",
      env: process.env
    });

    child.on("close", (code, signal) => resolve({ code: code ?? 1, signal }));
    child.on("error", () => resolve({ code: 1, signal: "error" }));
  });
}

async function main() {
  // Try real Next dev server first (best DX), but some locked-down Windows environments
  // block `child_process.fork` (EPERM). If it fails, fall back to a production preview
  // using `next build` + `next start` (no fork required).

  const dev = await runNode(NEXT_BIN, ["dev"]);
  if (dev.code === 0) return;

  console.warn(
    "\nNext.js dev server failed due to OS restrictions (child_process.fork -> EPERM). Falling back to production preview...\n"
  );

  // Use "server" mode for local preview (avoids relying on static export outputs and matches Next's normal runtime).
  // This still keeps the production deploy static by default (see `DASHBOARD_OUTPUT` in `next.config.mjs`).
  const originalMode = process.env.DASHBOARD_OUTPUT;
  process.env.DASHBOARD_OUTPUT = "server";

  const build = await runNode(NEXT_BIN, ["build"]);
  if (build.code !== 0) process.exit(build.code);

  console.log("\nStarting local preview server on http://localhost:3000 ...\n");
  const start = await runNode(NEXT_BIN, ["start", "-p", "3000"]);

  if (originalMode === undefined) delete process.env.DASHBOARD_OUTPUT;
  else process.env.DASHBOARD_OUTPUT = originalMode;

  process.exit(start.code);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
