/**
 * Offline place-name search over NISR hierarchy names.
 * Attribution: National Institute of Statistics of Rwanda (CC BY 4.0).
 * CHANGED 2026-11-01 GROK: normalised Kinyarwanda + trigram/edit-1
 */
export type PlaceRow = {
  code: string;
  level: "village" | "cell" | "sector" | "district" | "province";
  name: string;
  path: string;
  norm: string;
};

export function normalizeName(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[’‘`´]/g, "'")
    .replace(/[^a-z0-9'\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function trigrams(s: string): Set<string> {
  const t = `  ${s} `;
  const out = new Set<string>();
  for (let i = 0; i < t.length - 2; i++) out.add(t.slice(i, i + 3));
  return out;
}

function editDistance1(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false;
  if (a === b) return true;
  let i = 0, j = 0, edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++edits > 1) return false;
    if (a.length > b.length) i++;
    else if (a.length < b.length) j++;
    else { i++; j++; }
  }
  if (i < a.length || j < b.length) edits++;
  return edits <= 1;
}

export type SearchIndex = {
  rows: PlaceRow[];
  byPrefix: Map<string, number[]>; // first 3 chars of norm → row indices
};

export function buildIndex(rows: Omit<PlaceRow, "norm">[]): SearchIndex {
  const full: PlaceRow[] = rows.map((r) => ({ ...r, norm: normalizeName(r.name) }));
  const byPrefix = new Map<string, number[]>();
  full.forEach((r, i) => {
    const p = r.norm.slice(0, 3);
    if (!byPrefix.has(p)) byPrefix.set(p, []);
    byPrefix.get(p)!.push(i);
  });
  return { rows: full, byPrefix };
}

export function search(index: SearchIndex, query: string, limit = 10): PlaceRow[] {
  const q = normalizeName(query);
  if (!q) return [];
  const scored: { row: PlaceRow; score: number }[] = [];
  // exact / prefix candidates from first 3 chars + edit-1 scan of short list
  const prefixes = new Set<string>();
  prefixes.add(q.slice(0, 3));
  // also scan all rows if small; for 20k names full scan is fine on phone
  for (const row of index.rows) {
    let score = 0;
    if (row.norm === q) score = 100;
    else if (row.norm.startsWith(q)) score = 90;
    else if (q.startsWith(row.norm) && row.norm.length >= 3) score = 80;
    else if (editDistance1(row.norm, q)) score = 70;
    else {
      const A = trigrams(row.norm), B = trigrams(q);
      let inter = 0;
      for (const t of B) if (A.has(t)) inter++;
      const union = A.size + B.size - inter;
      const j = union ? inter / union : 0;
      if (j >= 0.35) score = Math.round(j * 60);
    }
    if (score > 0) scored.push({ row, score });
  }
  scored.sort((a, b) => b.score - a.score || a.row.level.localeCompare(b.row.level));
  return scored.slice(0, limit).map((s) => s.row);
}
