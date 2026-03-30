import type { SnapshotUpdate } from "../lib/types";

function riskBadgeClass(risk: SnapshotUpdate["risk_level"]) {
  if (risk === "high") return "badge danger";
  if (risk === "medium") return "badge warning";
  return "badge ok";
}

export default function UpdateCard({ update }: { update: SnapshotUpdate }) {
  const products = update.products.length ? update.products.join(", ") : "Unknown";

  return (
    <div className="card">
      <div className="card-top">
        <span className={riskBadgeClass(update.risk_level)}>{update.risk_level.toUpperCase()}</span>
        <span className="badge">{update.section}</span>
        <span className="badge">{update.jurisdiction}</span>
        <span className="badge">{update.category}</span>
      </div>

      <div className="title">{update.short_summary}</div>
      <div className="meta">
        <div>
          <strong>Products:</strong> {products}
        </div>
        <div>
          <strong>Why it matters:</strong> {update.why_it_matters}
        </div>
        <div>
          <strong>Source:</strong>{" "}
          <a href={update.source_url} target="_blank" rel="noreferrer">
            {update.source_url}
          </a>
        </div>
      </div>
    </div>
  );
}
