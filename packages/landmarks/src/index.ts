/** OSM landmarks nearby search. ODbL attribution required. CHANGED 2026-11-01 GROK; see docs/HANDOFF.md */
export type Landmark = { id: string; osm_id: number; name: string; type: string; lat: number; lng: number; gh5: string };
export type NearbyOpts = { radius_m?: number; types?: string[]; baseUrl?: string; loadTile?: (gh5: string) => Promise<Landmark[]> };

function haversine_m(a: number, b: number, c: number, d: number): number {
  const R = 6371000, toR = Math.PI / 180;
  const dLat = (c - a) * toR, dLon = (d - b) * toR;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a * toR) * Math.cos(c * toR) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

function encode5(lat: number, lon: number): string {
  const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";
  let idx = 0, bit = 0, even = true, latMin = -90, latMax = 90, lonMin = -180, lonMax = 180, gh = "";
  while (gh.length < 5) {
    if (even) { const mid = (lonMin + lonMax) / 2; if (lon >= mid) { idx = idx * 2 + 1; lonMin = mid; } else { idx = idx * 2; lonMax = mid; } }
    else { const mid = (latMin + latMax) / 2; if (lat >= mid) { idx = idx * 2 + 1; latMin = mid; } else { idx = idx * 2; latMax = mid; } }
    even = !even; if (++bit === 5) { gh += BASE32[idx]; bit = 0; idx = 0; }
  }
  return gh;
}

export async function nearby(lat: number, lng: number, opts: NearbyOpts = {}): Promise<(Landmark & { distance_m: number })[]> {
  const radius = opts.radius_m ?? 1000;
  const types = opts.types ? new Set(opts.types) : null;
  const centre = encode5(lat, lng);
  const tiles = [centre];
  const load = opts.loadTile ?? (async (gh5: string) => {
    if (!opts.baseUrl) return [];
    const url = `${opts.baseUrl.replace(/\/$/, "")}/${gh5}.json.gz`;
    const res = await fetch(url);
    if (!res.ok) return [];
    const buf = new Uint8Array(await res.arrayBuffer());
    if (typeof process !== "undefined" && process.versions?.node) {
      const zlib = await import("node:zlib");
      return JSON.parse(zlib.gunzipSync(Buffer.from(buf)).toString("utf8")) as Landmark[];
    }
    const stream = new Blob([buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text()) as Landmark[];
  });
  const all: Landmark[] = [];
  for (const t of tiles) all.push(...(await load(t)));
  return all
    .filter((x) => !types || types.has(x.type))
    .map((x) => ({ ...x, distance_m: haversine_m(lat, lng, x.lat, x.lng) }))
    .filter((x) => x.distance_m <= radius)
    .sort((a, b) => a.distance_m - b.distance_m);
}
