import Link from "next/link";

import { US_STATES } from "../lib/states";
import stateLaws from "../lib/state_laws.generated.json";

export default function Sidebar() {
  const data = stateLaws as unknown as { states?: Record<string, unknown> };
  const available = new Set(Object.keys(data.states || {}));
  return (
    <nav>
      <Link className="nav-item" href="/">
        Today
      </Link>
      <Link className="nav-item" href="/states">
        States
      </Link>
      <div style={{ height: 8 }} />
      {US_STATES.map((s) => (
        <Link
          key={s.code}
          className={`nav-item ${available.has(s.code) ? "" : "nav-item--empty"}`}
          href={`/states/${s.code}`}
        >
          {s.code} — {s.name} {!available.has(s.code) ? <span className="nav-meta">No data</span> : null}
        </Link>
      ))}
    </nav>
  );
}
