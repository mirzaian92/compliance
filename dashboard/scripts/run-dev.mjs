import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const NEXT_BIN = path.join(process.cwd(), "node_modules", "next", "dist", "bin", "next");

const NEXT_BUILD_ID = path.join(process.cwd(), ".next", "BUILD_ID");
const MODE_MARKER = path.join(process.cwd(), ".next", ".dashboard_output");

function hasServerBuild() {
  if (!fs.existsSync(NEXT_BUILD_ID)) return false;
  if (!fs.existsSync(MODE_MARKER)) return false;
  try {
    return fs.readFileSync(MODE_MARKER, "utf8").trim() === "server";
  } catch {
    return false;
  }
}
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

  if (!hasServerBuild()) {
    const build = await runNode(NEXT_BIN, ["build"]);
    if (build.code !== 0) process.exit(build.code);
    try {
      fs.writeFileSync(MODE_MARKER, "server\n", "utf8");
    } catch {
      // Best effort; marker only speeds up future runs.
    }
  } else {
    console.log("Using existing production build (.next) for local preview.");
  }

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
