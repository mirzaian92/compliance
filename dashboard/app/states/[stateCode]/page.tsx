import { notFound } from "next/navigation";

import { getStateByCode } from "../../../lib/states";

export const dynamic = "force-dynamic";

export default function StatePage({ params }: { params: { stateCode: string } }) {
  const code = (params.stateCode || "").toUpperCase();
  const st = getStateByCode(code);
  if (!st) return notFound();

  return (
    <div className="card">
      <div className="title">{st.name} ({st.code})</div>
      <div className="meta">
        Placeholder page. In a later phase, this route can show state-specific history, bills, and enforcement items.
      </div>
    </div>
  );
}

