import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";

let _db: Database.Database | null = null;

function resolveDbPath(): string {
  const explicit =
    process.env.DASHBOARD_DB_PATH || process.env.DB_PATH || process.env.COMPLIANCE_DB_PATH;
  if (explicit) return explicit;

  // Defaults:
  // - local Python runs often use ../compliance.db
  // - GitHub Actions uses DB_PATH=data/compliance.db (within repo root)
  const candidates = [
    path.resolve(process.cwd(), "..", "data", "compliance.db"),
    path.resolve(process.cwd(), "..", "compliance.db"),
    path.resolve(process.cwd(), "data", "compliance.db"),
    path.resolve(process.cwd(), "compliance.db")
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return candidates[0]!;
}

export function getDb(): Database.Database {
  if (_db) return _db;

  const dbPath = resolveDbPath();
  if (!fs.existsSync(dbPath)) {
    throw new Error(
      `SQLite DB not found at ${dbPath}. Set DASHBOARD_DB_PATH (recommended) or DB_PATH to the pipeline DB file.`
    );
  }

  // Read-only: this UI should not mutate pipeline state.
  _db = new Database(dbPath, { readonly: true, fileMustExist: true });
  return _db;
}

