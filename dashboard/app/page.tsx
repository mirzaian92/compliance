import { DateTime } from "luxon";

import UpdateCard from "../components/UpdateCard";
import { getDashboardData } from "../lib/data";

// This dashboard only needs to reflect daily changes. We still render dynamically so
// internal users always see the latest DB contents after the 7:00 AM pipeline runs.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  let data: Awaited<ReturnType<typeof getDashboardData>> | null = null;
  let loadError: string | null = null;
  try {
    data = await getDashboardData();
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  if (!data) {
    return (
      <div className="card">
        <div className="title">Dashboard not ready</div>
        <div className="meta">
          The dashboard reads from the pipeline SQLite DB. Ensure the Python pipeline has run at least once and set{" "}
          <code>DASHBOARD_DB_PATH</code> (or <code>DB_PATH</code>) to the same DB file.
        </div>
        <details>
          <summary>Show error</summary>
          <pre>{loadError}</pre>
        </details>
      </div>
    );
  }

  const todayLabel = DateTime.fromISO(data.digestDate).toLocaleString(DateTime.DATE_FULL);
  const generatedLabel = data.digestGeneratedAt
    ? DateTime.fromISO(data.digestGeneratedAt).toLocaleString(DateTime.DATETIME_MED_WITH_SECONDS)
    : "unknown";

  return (
    <>
      <div className="header">
        <div>
          <h2>Today’s Update</h2>
          <div className="subheader">
            Date: <strong>{todayLabel}</strong> • Generated: <strong>{generatedLabel}</strong>
          </div>
        </div>
        <div className="subheader">
          Refresh cadence: once daily after the 7:00 AM pipeline run
        </div>
      </div>

      <div className="grid">
        <div className="stat">
          <div className="label">Urgent</div>
          <div className="value">{data.counts.urgent}</div>
        </div>
        <div className="stat">
          <div className="label">Federal</div>
          <div className="value">{data.counts.federal}</div>
        </div>
        <div className="stat">
          <div className="label">State</div>
          <div className="value">{data.counts.state}</div>
        </div>
        <div className="stat">
          <div className="label">Watchlist</div>
          <div className="value">{data.counts.watchlist}</div>
        </div>
      </div>

      {data.updates.length === 0 ? (
        <div className="card">
          <div className="title">No significant updates</div>
          <div className="meta">
            No items were found for this digest date in <code>classified_updates</code>. The raw
            digest is still available below.
          </div>
        </div>
      ) : (
        <div className="feed">
          {data.updates.map((u) => (
            <UpdateCard key={u.id} update={u} />
          ))}
        </div>
      )}

      <details>
        <summary>View raw digest markdown (source of truth)</summary>
        <pre>{data.digestMarkdown ?? "No digest found in daily_digests."}</pre>
      </details>
    </>
  );
}
