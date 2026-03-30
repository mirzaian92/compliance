export type RiskLevel = "low" | "medium" | "high";
export type DashboardUpdateSection = "Urgent" | "Federal" | "State" | "Watchlist";

export type DigestCounts = { urgent: number; federal: number; state: number; watchlist: number };

// Snapshot JSON is produced by the Python pipeline via `python -m app.main export-dashboard`.
// We keep the snapshot schema intentionally small and stable so the UI can run on Vercel without DB access.
export type SnapshotUpdate = {
  id: number;
  raw_document_id: number;
  jurisdiction_level: "federal" | "state";
  jurisdiction_name: string;
  state_code: string | null;
  category: string;
  products: string[];
  risk_level: RiskLevel;
  action_needed: boolean;
  short_summary: string;
  why_it_matters: string;
  effective_date: string | null;
  status_label: string;
  confidence: number;
  source_url: string;
  created_at: string;
  section: DashboardUpdateSection;
  jurisdiction: string;
};

export type SnapshotData = {
  digest_date: string;
  generated_at: string | null;
  counts: DigestCounts;
  updates: SnapshotUpdate[];
  markdown: string | null;
};
