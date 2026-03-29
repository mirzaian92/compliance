import type { DashboardUpdate } from "../lib/types";

function riskBadgeClass(risk: DashboardUpdate["riskLevel"]) {
  if (risk === "high") return "badge danger";
  if (risk === "medium") return "badge warning";
  return "badge ok";
}

export default function UpdateCard({ update }: { update: DashboardUpdate }) {
  const products = update.products.length ? update.products.join(", ") : "Unknown";

  return (
    <div className="card">
      <div className="card-top">
        <span className={riskBadgeClass(update.riskLevel)}>{update.riskLevel.toUpperCase()}</span>
        <span className="badge">{update.section}</span>
        <span className="badge">{update.jurisdiction}</span>
        <span className="badge">{update.category}</span>
      </div>

      <div className="title">{update.shortSummary}</div>
      <div className="meta">
        <div>
          <strong>Products:</strong> {products}
        </div>
        <div>
          <strong>Why it matters:</strong> {update.whyItMatters}
        </div>
        <div>
          <strong>Source:</strong>{" "}
          <a href={update.sourceUrl} target="_blank" rel="noreferrer">
            {update.sourceUrl}
          </a>
        </div>
      </div>
    </div>
  );
}

