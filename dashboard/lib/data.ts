import fs from "node:fs/promises";
import path from "node:path";

import { DateTime } from "luxon";

import type { SnapshotData } from "./types";

function dashboardTimezone(): string {
  return process.env.DIGEST_TIMEZONE || "America/Los_Angeles";
}

function todayIsoInTz(tz: string): string {
  return DateTime.now().setZone(tz).toISODate() || DateTime.utc().toISODate()!;
}

function defaultSnapshotPath(): string {
  // Assumption: Vercel project root is `dashboard/`, and the snapshot is committed under `public/`.
  return path.join(process.cwd(), "public", "data", "latest.json");
}

export async function getDashboardData(): Promise<SnapshotData> {
  const tz = dashboardTimezone();
  const today = todayIsoInTz(tz);
  const snapshotPath = process.env.DASHBOARD_SNAPSHOT_PATH || defaultSnapshotPath();

  try {
    const raw = await fs.readFile(snapshotPath, "utf-8");
    const data = JSON.parse(raw) as SnapshotData;
    // Requirement: homepage shows ONLY today's update. If the snapshot is stale,
    // we still show it but the UI should communicate the mismatch.
    if (!data?.digest_date) throw new Error("Snapshot missing digest_date");
    return data;
  } catch {
    // If the snapshot doesn't exist yet, return an empty "today" payload.
    return {
      digest_date: today,
      generated_at: null,
      counts: { urgent: 0, federal: 0, state: 0, watchlist: 0 },
      updates: [],
      markdown: null
    };
  }
}
