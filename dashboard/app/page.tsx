import { DateTime } from "luxon";

import UpdateCard from "../components/UpdateCard";
import { getDashboardData } from "../lib/data";

// The dashboard reads a committed daily snapshot; render dynamically so Vercel always serves
// the latest deployed snapshot without needing a rebuild-time import.
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
          The dashboard reads from a daily snapshot JSON file. Ensure the GitHub Actions daily run is exporting a snapshot
          to <code>dashboard/public/data/latest.json</code>, or set <code>DASHBOARD_SNAPSHOT_PATH</code>.
        </div>
        <details>
          <summary>Show error</summary>
          <pre>{loadError}</pre>
        </details>
      </div>
    );
  }

  const tz = process.env.DIGEST_TIMEZONE || "America/Los_Angeles";
  const expectedDate = DateTime.now().setZone(tz).toISODate() || DateTime.utc().toISODate()!;
  const isForToday = data.digest_date === expectedDate;
  const display = isForToday
    ? data
    : { ...data, digest_date: expectedDate, generated_at: null, counts: { urgent: 0, federal: 0, state: 0, watchlist: 0 }, updates: [], markdown: null };

  const todayLabel = DateTime.fromISO(display.digest_date).toLocaleString(DateTime.DATE_FULL);
  const generatedLabel = display.generated_at
    ? DateTime.fromISO(display.generated_at).toLocaleString(DateTime.DATETIME_MED_WITH_SECONDS)
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
          <div className="value">{display.counts.urgent}</div>
        </div>
        <div className="stat">
          <div className="label">Federal</div>
          <div className="value">{display.counts.federal}</div>
        </div>
        <div className="stat">
          <div className="label">State</div>
          <div className="value">{display.counts.state}</div>
        </div>
        <div className="stat">
          <div className="label">Watchlist</div>
          <div className="value">{display.counts.watchlist}</div>
        </div>
      </div>

      {!isForToday ? (
        <div className="card">
          <div className="title">Today’s digest isn’t available yet</div>
          <div className="meta">
            The dashboard only shows the current day’s update. Check back after the scheduled 7:00 AM pipeline run
            ({tz}).
          </div>
        </div>
      ) : display.updates.length === 0 ? (
        <div className="card">
          <div className="title">No significant updates</div>
          <div className="meta">
            No items were included in today’s snapshot. The raw digest markdown (if present) is still available below.
          </div>
        </div>
      ) : (
        <div className="feed">
          {display.updates.map((u) => (
            <UpdateCard key={u.id} update={u} />
          ))}
        </div>
      )}

      <details>
        <summary>View raw digest markdown (source of truth)</summary>
        <pre>{display.markdown ?? "No digest markdown found in snapshot."}</pre>
      </details>
    </>
  );
}
