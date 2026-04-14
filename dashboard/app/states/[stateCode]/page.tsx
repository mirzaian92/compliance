import { notFound } from "next/navigation";

import { US_STATES, getStateByCode } from "../../../lib/states";
import stateLaws from "../../../lib/state_laws.generated.json";

export const dynamic = "force-static";

export function generateStaticParams() {
  return US_STATES.map((s) => ({ stateCode: s.code }));
}

type StateLawSource = { label: string; url: string };
type StateLawCompound = { compound: string; status: string; notes: string };
type StateLawSection = {
  state_code: string;
  state_name: string;
  last_verified: string | null;
  sources: StateLawSource[];
  compounds: StateLawCompound[];
  regulatory_notes: string | null;
  raw_markdown: string;
};

function renderParagraphs(text: string) {
  return text
    .split(/\n\s*\n/g)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p, idx) => (
      <p key={idx} className="p">
        {p.split("\n").map((line, i) => (
          <span key={i}>
            {line}
            {i < p.split("\n").length - 1 ? <br /> : null}
          </span>
        ))}
      </p>
    ));
}

export default function StatePage({ params }: { params: { stateCode: string } }) {
  const code = (params.stateCode || "").toUpperCase();
  const st = getStateByCode(code);
  if (!st) return notFound();

  const data = stateLaws as unknown as { generated_at: string; states: Record<string, StateLawSection> };
  const law = data.states[code];

  return (
    <>
      <div className="header">
        <div>
          <h2>{st.name}</h2>
          <div className="subheader">
            State code: <strong>{st.code}</strong>
            {law?.last_verified ? (
              <>
                {" "}
                • Last verified: <strong>{law.last_verified}</strong>
              </>
            ) : null}
          </div>
        </div>
        <div className="subheader">Data generated: {data.generated_at}</div>
      </div>

      {!law ? (
        <div className="card">
          <div className="title">No state-specific law data loaded</div>
          <div className="meta">
            This dashboard reads state law sections from markdown files in <code>dashboard/content/</code>. This state
            isn’t in the current markdown set yet.
          </div>
        </div>
      ) : (
        <>
          <div className="card">
            <div className="title">Sources</div>
            <div className="meta">
              {law.sources.length ? (
                <ul className="list">
                  {law.sources.map((s) => (
                    <li key={s.url}>
                      <a href={s.url} target="_blank" rel="noreferrer">
                        {s.label}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                "No sources parsed for this section."
              )}
            </div>
          </div>

          <div className="card">
            <div className="title">Product / compound status</div>
            {law.compounds.length ? (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Compound</th>
                      <th>Status</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {law.compounds.map((r) => (
                      <tr key={r.compound}>
                        <td className="mono">{r.compound}</td>
                        <td>{r.status}</td>
                        <td>{r.notes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="meta">No table parsed for this state section.</div>
            )}
          </div>

          <div className="card">
            <div className="title">Regulatory notes</div>
            <div className="meta">{law.regulatory_notes ? renderParagraphs(law.regulatory_notes) : "None provided."}</div>
          </div>

          <details>
            <summary>View raw markdown (for verification)</summary>
            <pre>{law.raw_markdown}</pre>
          </details>
        </>
      )}
    </>
  );
}
