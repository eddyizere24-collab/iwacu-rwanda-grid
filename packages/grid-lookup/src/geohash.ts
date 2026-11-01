const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";
export function encode(lat: number, lon: number, precision: number): string {
  let idx = 0, bit = 0, evenBit = true;
  let latMin = -90, latMax = 90, lonMin = -180, lonMax = 180;
  let geohash = "";
  while (geohash.length < precision) {
    if (evenBit) {
      const mid = (lonMin + lonMax) / 2;
      if (lon >= mid) { idx = idx * 2 + 1; lonMin = mid; } else { idx = idx * 2; lonMax = mid; }
    } else {
      const mid = (latMin + latMax) / 2;
      if (lat >= mid) { idx = idx * 2 + 1; latMin = mid; } else { idx = idx * 2; latMax = mid; }
    }
    evenBit = !evenBit;
    if (++bit === 5) { geohash += BASE32[idx]; bit = 0; idx = 0; }
  }
  return geohash;
}
