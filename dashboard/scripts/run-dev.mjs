import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const NEXT_BIN = path.join(process.cwd(), "node_modules", "next", "dist", "bin", "next");

function runNode(scriptPath, args, { captureStderr = false } = {}) {
  return new Promise((resolve) => {
    let stderrBuf = "";
    const child = spawn(process.execPath, [scriptPath, ...args], {
      stdio: ["inherit", "inherit", "pipe"],
      env: process.env
    });

    child.stderr.on("data", (d) => {
      const s = d.toString("utf8");
      process.stderr.write(s);
      if (captureStderr && stderrBuf.length < 16_384) stderrBuf += s;
    });

    child.on("close", (code, signal) => resolve({ code: code ?? 1, signal, stderrBuf }));
    child.on("error", (err) => resolve({ code: 1, signal: "error", stderrBuf: String(err) }));
  });
}

async function main() {
  // Try real Next dev server first (best DX), but some locked-down Windows environments
  // block `child_process.fork` (EPERM). In that case, fall back to a static export + local
  // static server on port 3000 so the dashboard can still be previewed.

  const dev = await runNode(NEXT_BIN, ["dev"], { captureStderr: true });
  if (dev.code === 0) return;

  const looksLikeForkBlocked =
    dev.stderrBuf.includes("spawn EPERM") || dev.stderrBuf.includes("child_process") || dev.stderrBuf.includes("fork");

  if (!looksLikeForkBlocked) {
    process.exit(dev.code);
  }

  console.warn(
    "\nNext.js dev server failed due to OS restrictions (child_process.fork -> EPERM). Falling back to static preview...\n"
  );

  const build = await runNode(NEXT_BIN, ["build"]);
  if (build.code !== 0) process.exit(build.code);

  const serveOutPath = path.join(__dirname, "serve-out.mjs");
  const serve = await runNode(serveOutPath, []);
  process.exit(serve.code);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

