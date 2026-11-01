/** Style factory with configurable relative base URL. CHANGED 2026-11-01 GROK; see docs/HANDOFF.md */
import styleTemplate from "./style.json" with { type: "json" };

export type StyleOpts = { baseUrl?: string };

export function buildStyle(opts: StyleOpts = {}): Record<string, unknown> {
  const base = (opts.baseUrl ?? "..").replace(/\/$/, "");
  const style = JSON.parse(JSON.stringify(styleTemplate)) as {
    sources?: Record<string, { url?: string }>;
    glyphs?: string;
    sprite?: string;
  };
  if (style.sources?.protomaps) {
    style.sources.protomaps.url = `pmtiles://${base}/rwanda.pmtiles`;
  }
  style.glyphs = `${base}/vendor/fonts/{fontstack}/{range}.pbf`;
  return style as Record<string, unknown>;
}

export { styleTemplate };
