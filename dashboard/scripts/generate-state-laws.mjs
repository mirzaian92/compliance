import fs from "node:fs";
import path from "node:path";

const NAME_TO_CODE = {
  alabama: "AL",
  alaska: "AK",
  arizona: "AZ",
  arkansas: "AR",
  california: "CA",
  colorado: "CO",
  connecticut: "CT",
  delaware: "DE",
  florida: "FL",
  georgia: "GA",
  hawaii: "HI",
  idaho: "ID",
  illinois: "IL",
  indiana: "IN",
  iowa: "IA",
  kansas: "KS",
  kentucky: "KY",
  louisiana: "LA",
  maine: "ME",
  maryland: "MD",
  massachusetts: "MA",
  michigan: "MI",
  minnesota: "MN",
  mississippi: "MS",
  missouri: "MO",
  montana: "MT",
  nebraska: "NE",
  nevada: "NV",
  "new hampshire": "NH",
  "new jersey": "NJ",
  "new mexico": "NM",
  "new york": "NY",
  "north carolina": "NC",
  "north dakota": "ND",
  ohio: "OH",
  oklahoma: "OK",
  oregon: "OR",
  pennsylvania: "PA",
  "rhode island": "RI",
  "south carolina": "SC",
  "south dakota": "SD",
  tennessee: "TN",
  texas: "TX",
  utah: "UT",
  vermont: "VT",
  virginia: "VA",
  washington: "WA",
  "west virginia": "WV",
  wisconsin: "WI",
  wyoming: "WY"
};

function fixMojibake(input) {
  // The source markdown appears to contain common UTF-8->cp1252 mojibake.
  // Apply a conservative replacement table (deterministic, no guessing).
  const replacements = [
    ["Â§", "§"],
    ["â€”", "—"],
    ["â€“", "–"],
    ["â€œ", "“"],
    ["â€", "”"],
    ["â€˜", "‘"],
    ["â€™", "’"],
    ["â€¦", "…"],
    ["â‰¤", "≤"],
    ["â‰¥", "≥"],
    ["Ã—", "×"],
    ["Â¢", "¢"],
    ["âœ…", "✅"],
    ["ðŸš«", "🚫"],
    ["âš ï¸", "⚠️"],
    ["â“", "❓"]
  ];
  let out = input;
  for (const [from, to] of replacements) out = out.split(from).join(to);
  return out;
}

function parseSourcesLine(sourcesText) {
  const sources = [];
  const re = /\[([^\]]+)\]\(([^)]+)\)/g;
  let match;
  while ((match = re.exec(sourcesText)) !== null) {
    sources.push({ label: match[1].trim(), url: match[2].trim() });
  }
  return sources;
}

function parseTableRows(lines, startIndex) {
  // Expects:
  // | Compound | Status | Notes |
  // |----------|--------|-------|
  // | THCa | ✅ Legal | ... |
  const rows = [];
  for (let idx = startIndex + 2; idx < lines.length; idx++) {
    const line = lines[idx].trim();
    if (!line.startsWith("|")) break;
    const parts = line
      .split("|")
      .slice(1, -1)
      .map((p) => p.trim());
    if (parts.length < 2) continue;
    rows.push({
      compound: parts[0] || "",
      status: parts[1] || "",
      notes: parts[2] || ""
    });
  }
  return rows;
}

function stripParensSuffix(title) {
  return title.replace(/\s*\([^)]*\)\s*$/, "").trim();
}

function parseMarkdown(md, generatedAt) {
  const normalized = fixMojibake(md).replace(/\r\n/g, "\n");
  const chunks = normalized.split(/^###\s+/m);
  chunks.shift(); // preamble

  const states = {};
  for (const chunk of chunks) {
    const lines = chunk.split("\n");
    const heading = (lines[0] || "").trim();
    if (!heading) continue;

    const stateName = stripParensSuffix(heading);
    const stateCode = NAME_TO_CODE[stateName.toLowerCase()];
    if (!stateCode) continue;

    const body = lines.slice(1).join("\n");

    const lastVerifiedMatch = body.match(/^\*\*Last verified:\*\*\s*(.+)\s*$/m);
    const sourcesMatch = body.match(/^\*\*Sources:\*\*\s*(.+)\s*$/m);
    const lastVerified = lastVerifiedMatch ? lastVerifiedMatch[1].trim() : null;
    const sources = sourcesMatch ? parseSourcesLine(sourcesMatch[1]) : [];

    let compounds = [];
    const tableHeaderIndex = lines.findIndex((l) => l.trim().startsWith("| Compound |"));
    if (tableHeaderIndex !== -1) {
      compounds = parseTableRows(lines, tableHeaderIndex);
    }

    let regulatoryNotes = null;
    const regIdx = lines.findIndex((l) => l.includes("**Regulatory notes:**"));
    if (regIdx !== -1) {
      const firstLine = lines[regIdx];
      const after = firstLine.split("**Regulatory notes:**")[1] || "";
      const rest = [after.trim(), ...lines.slice(regIdx + 1)]
        .join("\n")
        .trim()
        .replace(/^---\s*$/gm, "")
        .trim();
      regulatoryNotes = rest || null;
    }

    const rawSection = `### ${heading}\n${lines.slice(1).join("\n")}`.trim();

    states[stateCode] = {
      state_code: stateCode,
      state_name: stateName,
      last_verified: lastVerified,
      sources,
      compounds,
      regulatory_notes: regulatoryNotes,
      raw_markdown: rawSection
    };
  }

  return { generated_at: generatedAt, states };
}

function main() {
  const inputPath = path.join(process.cwd(), "content", "state_laws.md");
  const outPath = path.join(process.cwd(), "lib", "state_laws.generated.json");

  if (!fs.existsSync(inputPath)) {
    console.error(`state laws input markdown not found: ${inputPath}`);
    process.exit(1);
  }

  const inputStats = fs.statSync(inputPath);
  const generatedAt = inputStats.mtime.toISOString();
  const md = fs.readFileSync(inputPath, "utf8");
  const parsed = parseMarkdown(md, generatedAt);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const next = JSON.stringify(parsed, null, 2) + "\n";

  if (fs.existsSync(outPath)) {
    const prev = fs.readFileSync(outPath, "utf8");
    if (prev === next) {
      const count = Object.keys(parsed.states).length;
      console.log(`State laws already up to date (${count} sections).`);
      return;
    }
  }

  fs.writeFileSync(outPath, next, "utf8");

  const count = Object.keys(parsed.states).length;
  console.log(`Generated ${count} state sections -> ${path.relative(process.cwd(), outPath)}`);
}

main();
