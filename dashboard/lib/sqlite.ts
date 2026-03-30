// Deprecated: the dashboard now runs from a committed JSON snapshot so it can be deployed to Vercel
// without requiring SQLite access or native Node modules.
//
// This file is intentionally left as a stub for future work if you decide to re-introduce
// direct DB reads (for example on a long-running server).

export function getDb(): never {
  throw new Error("SQLite mode is disabled. Use the JSON snapshot produced by `python -m app.main export-dashboard`.");
}
