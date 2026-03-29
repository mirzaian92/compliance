export type JurisdictionLevel = "federal" | "state";
export type RiskLevel = "low" | "medium" | "high";

export type DigestCounts = {
  urgent: number;
  federal: number;
  state: number;
  watchlist: number;
};

export type DashboardUpdateSection = "Urgent" | "Federal" | "State" | "Watchlist";

export type DashboardUpdate = {
  id: number;
  rawDocumentId: number;
  jurisdictionLevel: JurisdictionLevel;
  jurisdictionName: string;
  stateCode: string | null;
  category: string;
  products: string[];
  riskLevel: RiskLevel;
  actionNeeded: boolean;
  shortSummary: string;
  whyItMatters: string;
  effectiveDate: string | null;
  statusLabel: string;
  confidence: number;
  sourceUrl: string;
  createdAt: string;

  section: DashboardUpdateSection;
  jurisdiction: string;
};

export type DashboardData = {
  digestDate: string;
  digestGeneratedAt: string | null;
  digestMarkdown: string | null;
  counts: DigestCounts;
  updates: DashboardUpdate[];
};

