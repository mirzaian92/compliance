import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const OUT_DIR = path.resolve(__dirname, "..", "out");
const PORT = Number.parseInt(process.env.PORT || "3000", 10);

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
  ".webp": "image/webp"
};

function safeDecodeURIComponent(s) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

function resolveCandidatePaths(urlPath) {
  const cleaned = urlPath.split("?")[0].split("#")[0];
  const decoded = safeDecodeURIComponent(cleaned);

  const rel = decoded.replace(/^\/+/, "");
  const normalized = rel.replace(/\.\.+/g, "."); // minimal traversal hardening

  const candidates = [];
  if (!normalized || normalized.endsWith("/")) {
    candidates.push(path.join(OUT_DIR, normalized, "index.html"));
  } else {
    candidates.push(path.join(OUT_DIR, normalized));
    candidates.push(path.join(OUT_DIR, normalized + ".html"));
    candidates.push(path.join(OUT_DIR, normalized, "index.html"));
  }
  return candidates;
}

function findFile(urlPath) {
  for (const candidate of resolveCandidatePaths(urlPath)) {
    const resolved = path.resolve(candidate);
    if (!resolved.startsWith(OUT_DIR)) continue;
    if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) return resolved;
  }
  const notFound = path.join(OUT_DIR, "404.html");
  if (fs.existsSync(notFound)) return notFound;
  return null;
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return CONTENT_TYPES[ext] || "application/octet-stream";
}

function main() {
  if (!fs.existsSync(OUT_DIR)) {
    console.error(`Missing ${OUT_DIR}. Run \`npm run build\` first.`);
    process.exit(1);
  }

  const server = http.createServer((req, res) => {
    const target = findFile(req.url || "/");
    if (!target) {
      res.statusCode = 404;
      res.setHeader("content-type", "text/plain; charset=utf-8");
      res.end("Not Found");
      return;
    }

    const is404 = target.endsWith(path.sep + "404.html");
    res.statusCode = is404 ? 404 : 200;
    res.setHeader("content-type", contentTypeFor(target));
    res.end(fs.readFileSync(target));
  });

  server.listen(PORT, "127.0.0.1", () => {
    console.log(`Serving static dashboard from ${OUT_DIR}`);
    console.log(`Open: http://localhost:${PORT}`);
    console.log("Press Ctrl+C to stop.");
  });
}

main();

