import styleTemplate from "./style.json" with { type: "json" };

export type StyleOptions = {
  /** Base URL without trailing slash (pmtiles, glyphs, optional boundaries). */
  baseUrl: string;
  /** Optional GeoJSON/vector URL for village/district boundaries; layer off if omitted. */
  boundariesUrl?: string;
};

/** Build a MapLibre style object with configurable asset base URL. */
export function buildStyle(opts: StyleOptions): Record<string, unknown> {
  const base = opts.baseUrl.replace(/\/$/, "");
  const raw = JSON.stringify(styleTemplate).replaceAll("__BASE__", base);
  const style = JSON.parse(raw) as Record<string, unknown>;
  if (opts.boundariesUrl) {
    const sources = style.sources as Record<string, unknown>;
    sources.boundaries = { type: "geojson", data: opts.boundariesUrl };
    const layers = style.layers as unknown[];
    layers.push({
      id: "admin-boundaries",
      type: "line",
      source: "boundaries",
      paint: { "line-color": "#b45309", "line-width": 1.2, "line-opacity": 0.8 },
    });
  }
  return style;
}

export const REQUIRED_SOURCE_LAYERS = [
  "water",
  "waterway",
  "landcover",
  "landuse",
  "park",
  "boundary",
  "transportation",
  "transportation_name",
  "building",
  "place",
  "poi",
  "mountain_peak",
] as const;
