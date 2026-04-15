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
    ["â€¢", "•"],
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

function stripMarkdownInline(text) {
  return text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1").trim();
}

function parseFileAsOf(md) {
  // Examples:
  // "# ... — Massachusetts through North Carolina — As of April 11, 2026"
  // "## ... (April 2026)"
  const m =
    md.match(/\bAs of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\b/i) ||
    md.match(/\bAs of\s+([A-Za-z]+\s+\d{4})\b/i) ||
    md.match(/\((January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\)/i);
  if (!m) return null;
  return stripMarkdownInline(m[1] || m[0]).replace(/^\(|\)$/g, "").trim();
}

function parseMasterStateTables(lines, defaultLastVerified) {
  const byState = {};

  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] || "").trim();
    if (!line.toLowerCase().startsWith("| state |")) continue;

    const headerParts = line
      .split("|")
      .slice(1, -1)
      .map((p) => p.trim());

    // Skip the separator row (|---|---|...)
    const sep = (lines[i + 1] || "").trim();
    if (!sep.startsWith("|")) continue;

    const headers = headerParts.slice(1); // everything after "State"

    for (let r = i + 2; r < lines.length; r++) {
      const rowLine = (lines[r] || "").trim();
      if (!rowLine.startsWith("|")) break;

      const cols = rowLine
        .split("|")
        .slice(1, -1)
        .map((c) => c.trim());
      if (cols.length < 2) continue;

      const stateCell = stripMarkdownInline(cols[0] || "");
      const stateName = stripParensSuffix(stateCell);
      const stateCode = NAME_TO_CODE[stateName.toLowerCase()];
      if (!stateCode) continue;

      const compounds = [];
      for (let c = 0; c < headers.length; c++) {
        const compoundHeader = stripMarkdownInline(headers[c] || "");
        const status = stripMarkdownInline(cols[c + 1] || "");
        if (!compoundHeader) continue;
        if (!status) continue;
        compounds.push({ compound: compoundHeader, status, notes: "" });
      }

      byState[stateCode] = {
        state_code: stateCode,
        state_name: stateName,
        last_verified: defaultLastVerified,
        sources: [],
        compounds,
        regulatory_notes: null,
        raw_markdown: rowLine
      };
    }
  }

  return byState;
}

function parseStateBullets(normalizedMd, defaultLastVerified) {
  // Pull any "- **State** — <summary>" bullet lines and attach them as "watchlist" notes.
  const byState = {};
  const lines = normalizedMd.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("- **")) continue;
    const m = trimmed.match(/^- \*\*([^*]+)\*\*\s*[—:-]\s*(.+)\s*$/);
    if (!m) continue;
    const stateName = stripParensSuffix(stripMarkdownInline(m[1] || ""));
    const stateCode = NAME_TO_CODE[stateName.toLowerCase()];
    if (!stateCode) continue;
    const note = stripMarkdownInline(m[2] || "");
    if (!note) continue;
    byState[stateCode] = {
      state_code: stateCode,
      state_name: stateName,
      last_verified: defaultLastVerified,
      sources: [],
      compounds: [],
      regulatory_notes: note,
      raw_markdown: trimmed
    };
  }
  return byState;
}

function parseInlineStateLists(normalizedMd, defaultLastVerified) {
  // Example:
  // **Key KCPA states ...:**\nArizona, Colorado, ...
  const byState = {};
  const lines = normalizedMd.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] || "").trim();
    if (!line.toLowerCase().includes("key kcpa states")) continue;
    const next = (lines[i + 1] || "").trim();
    if (!next) continue;
    const listText = stripMarkdownInline(next);
    const parts = listText.split(",").map((p) => p.trim()).filter(Boolean);
    for (const p of parts) {
      const stateName = stripParensSuffix(p.replace(/\s*\([^)]*\)\s*$/, "").trim());
      const stateCode = NAME_TO_CODE[stateName.toLowerCase()];
      if (!stateCode) continue;
      byState[stateCode] = {
        state_code: stateCode,
        state_name: stateName,
        last_verified: defaultLastVerified,
        sources: [],
        compounds: [],
        regulatory_notes: "Listed as a KCPA (Kratom Consumer Protection Act) framework state for kratom/7‑OH distribution in this report.",
        raw_markdown: `${line}\n${next}`.trim()
      };
    }
  }
  return byState;
}

function parseMarkdown(md, generatedAt) {
  const normalized = fixMojibake(md).replace(/\r\n/g, "\n");
  const defaultLastVerified = parseFileAsOf(normalized);
  const linesAll = normalized.split("\n");

  const fromMasterTable = parseMasterStateTables(linesAll, defaultLastVerified);
  const fromBullets = parseStateBullets(normalized, defaultLastVerified);
  const fromInlineLists = parseInlineStateLists(normalized, defaultLastVerified);

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

  // Fill gaps using the master table (less detailed, but better than nothing).
  for (const [code, section] of Object.entries(fromMasterTable)) {
    if (!states[code]) states[code] = section;
    else if (states[code].compounds.length === 0 && section.compounds.length) states[code].compounds = section.compounds;
    if (states[code].last_verified === null && section.last_verified) states[code].last_verified = section.last_verified;
  }

  // Attach watchlist/favorable bullet summaries as conservative notes. Do not overwrite full detail sections.
  for (const [code, section] of Object.entries({ ...fromInlineLists, ...fromBullets })) {
    if (!states[code]) {
      states[code] = section;
      continue;
    }
    const existing = states[code].regulatory_notes;
    const nextNote = section.regulatory_notes;
    if (!nextNote) continue;
    if (!existing) states[code].regulatory_notes = nextNote;
    else if (!existing.includes(nextNote)) states[code].regulatory_notes = `${existing}\n\nWatchlist summary: ${nextNote}`;
  }

  return { generated_at: generatedAt, states };
}

function main() {
  const contentDir = path.join(process.cwd(), "content");
  const outPath = path.join(process.cwd(), "lib", "state_laws.generated.json");

  if (!fs.existsSync(contentDir)) {
    console.error(`state laws content directory not found: ${contentDir}`);
    process.exit(1);
  }

  const mdFiles = fs
    .readdirSync(contentDir)
    .filter((n) => n.toLowerCase().endsWith(".md"))
    .sort((a, b) => a.localeCompare(b));

  if (mdFiles.length === 0) {
    console.error(`No markdown files found under: ${contentDir}`);
    process.exit(1);
  }

  const inputs = mdFiles.map((name) => {
    const fullPath = path.join(contentDir, name);
    const stat = fs.statSync(fullPath);
    return { name, fullPath, mtimeMs: stat.mtimeMs, mtimeIso: stat.mtime.toISOString() };
  });

  // Prefer the newest content as the "generated_at" signal so the UI can show when it was last updated.
  const generatedAt = inputs.reduce((acc, cur) => (cur.mtimeMs > acc.mtimeMs ? cur : acc), inputs[0]).mtimeIso;

  // Merge per-state sections across files. If the same state appears in multiple inputs,
  // the newest file wins (deterministic; also easiest to reason about).
  inputs.sort((a, b) => a.mtimeMs - b.mtimeMs || a.name.localeCompare(b.name));
  const mergedStates = {};
  const provenance = {};

  for (const input of inputs) {
    const md = fs.readFileSync(input.fullPath, "utf8");
    const parsed = parseMarkdown(md, generatedAt);
    for (const [code, section] of Object.entries(parsed.states)) {
      mergedStates[code] = section;
      provenance[code] = input.name;
    }
  }

  const finalDoc = { generated_at: generatedAt, states: mergedStates, provenance };

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const next = JSON.stringify(finalDoc, null, 2) + "\n";

  if (fs.existsSync(outPath)) {
    const prev = fs.readFileSync(outPath, "utf8");
    if (prev === next) {
      const count = Object.keys(finalDoc.states).length;
      console.log(`State laws already up to date (${count} sections).`);
      return;
    }
  }

  fs.writeFileSync(outPath, next, "utf8");

  const count = Object.keys(finalDoc.states).length;
  console.log(`Generated ${count} state sections -> ${path.relative(process.cwd(), outPath)}`);
}

main();
