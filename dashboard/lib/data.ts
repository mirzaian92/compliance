import { DateTime } from "luxon";

import { getDb } from "./sqlite";
import type { DashboardData, DashboardUpdate, DashboardUpdateSection, DigestCounts } from "./types";

function safeJsonArray(text: unknown): string[] {
  if (typeof text !== "string" || !text.trim()) return [];
  try {
    const v = JSON.parse(text);
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function dashboardTimezone(): string {
  // Reuse the pipeline scheduling timezone by default.
  return process.env.DIGEST_TIMEZONE || "America/Los_Angeles";
}

function todayIsoInTz(tz: string): string {
  return DateTime.now().setZone(tz).toISODate() || DateTime.utc().toISODate()!;
}

function classifySection(u: DashboardUpdate): DashboardUpdateSection {
  const isUrgent =
    u.riskLevel === "high" ||
    ["warning_letter", "recall", "enforcement_action"].includes(u.category);
  if (isUrgent) return "Urgent";

  const isWatch =
    u.statusLabel === "proposed" || ["bill_introduced", "proposed_rule"].includes(u.category);
  if (isWatch) return "Watchlist";

  if (u.jurisdictionLevel === "federal") return "Federal";
  return "State";
}

function computeCounts(updates: DashboardUpdate[]): DigestCounts {
  const counts: DigestCounts = { urgent: 0, federal: 0, state: 0, watchlist: 0 };
  for (const u of updates) {
    if (u.section === "Urgent") counts.urgent += 1;
    else if (u.section === "Federal") counts.federal += 1;
    else if (u.section === "State") counts.state += 1;
    else if (u.section === "Watchlist") counts.watchlist += 1;
  }
  return counts;
}

export async function getDashboardData(): Promise<DashboardData> {
  const tz = dashboardTimezone();
  const digestDate = todayIsoInTz(tz);
  const db = getDb();

  // Requirement: homepage shows ONLY today's update.
  // If today's digest hasn't been generated yet (e.g., before the 7:00 AM pipeline run),
  // we intentionally do not fall back to an older digest.
  const digestRow = db
    .prepare("SELECT digest_date, markdown_body, created_at FROM daily_digests WHERE digest_date = ? LIMIT 1")
    .get(digestDate);

  const resolvedDate = digestDate;
  const digestMarkdown = (digestRow?.markdown_body as string | undefined) || null;
  const digestGeneratedAt = (digestRow?.created_at as string | undefined) || null;

  // Pull all classified items for the digest date in the configured timezone.
  // We do this by converting the local day's [start, end) to UTC, then filtering created_at (stored as ISO UTC).
  const startUtc = DateTime.fromISO(`${resolvedDate}T00:00:00`, { zone: tz }).toUTC();
  const endUtc = startUtc.plus({ days: 1 });

  const rows = db
    .prepare(
      `
      SELECT
        id,
        raw_document_id,
        jurisdiction_level,
        jurisdiction_name,
        state_code,
        category,
        products_json,
        risk_level,
        action_needed,
        short_summary,
        why_it_matters,
        effective_date,
        status_label,
        confidence,
        source_url,
        created_at
      FROM classified_updates
      WHERE created_at >= ? AND created_at < ?
      ORDER BY created_at DESC
      `
    )
    .all(startUtc.toISO(), endUtc.toISO());

  const updates: DashboardUpdate[] = rows.map((r: any) => {
    const jurisdiction = r.jurisdiction_level === "federal" ? "Federal" : r.jurisdiction_name;
    const u: DashboardUpdate = {
      id: Number(r.id),
      rawDocumentId: Number(r.raw_document_id),
      jurisdictionLevel: r.jurisdiction_level,
      jurisdictionName: String(r.jurisdiction_name),
      stateCode: r.state_code ? String(r.state_code) : null,
      category: String(r.category),
      products: safeJsonArray(r.products_json),
      riskLevel: r.risk_level,
      actionNeeded: Boolean(r.action_needed),
      shortSummary: String(r.short_summary),
      whyItMatters: String(r.why_it_matters),
      effectiveDate: r.effective_date ? String(r.effective_date) : null,
      statusLabel: String(r.status_label),
      confidence: Number(r.confidence),
      sourceUrl: String(r.source_url),
      createdAt: String(r.created_at),
      section: "State",
      jurisdiction
    };
    u.section = classifySection(u);
    return u;
  });

  // Sort to match the digest expectation: urgent first, then federal, state, watchlist.
  const sectionRank: Record<DashboardUpdateSection, number> = {
    Urgent: 0,
    Federal: 1,
    State: 2,
    Watchlist: 3
  };
  updates.sort((a, b) => {
    const ra = sectionRank[a.section];
    const rb = sectionRank[b.section];
    if (ra !== rb) return ra - rb;
    // Within section, higher risk first, then newest first.
    const riskRank = (x: DashboardUpdate["riskLevel"]) => (x === "high" ? 0 : x === "medium" ? 1 : 2);
    const rr = riskRank(a.riskLevel) - riskRank(b.riskLevel);
    if (rr !== 0) return rr;
    return b.createdAt.localeCompare(a.createdAt);
  });

  return {
    digestDate: resolvedDate,
    digestGeneratedAt,
    digestMarkdown,
    counts: computeCounts(updates),
    updates
  };
}
