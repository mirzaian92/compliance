import Link from "next/link";

import { US_STATES } from "../lib/states";

export default function Sidebar() {
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
        <Link key={s.code} className="nav-item" href={`/states/${s.code}`}>
          {s.code} — {s.name}
        </Link>
      ))}
    </nav>
  );
}
