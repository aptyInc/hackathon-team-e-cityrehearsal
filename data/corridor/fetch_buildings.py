"""Fetch Overture Maps building footprints along the Lingampally -> Lakdikapul corridor.

Writes, for the 3D view (deck.gl extruded polygons):
  data/corridor/buildings/<point_id>.geojson   buildings in a ~900 m square around each corridor point
  data/corridor/buildings/route_band.geojson   buildings within BAND_M of the route that are in no point square
  data/corridor/buildings/index.json           {point_id: {file, count, bbox, size_kb, ...}}

Each building appears in exactly one file: where point squares overlap (e.g. j08/j09) it goes to the
nearest point. Draw all files together for the whole corridor without duplicates.

Properties per feature (all else dropped, coordinates rounded to 6 decimals):
  id              first 12 hex characters of the Overture GERS id
  height          metres, from Overture; if missing, num_floors x 3.2; else null
  num_floors      from Overture, or null
  render_height_m height to draw: `height` if known, else floors assumed from footprint area
                  (same rule as data/raw/ymca_buildings.geojson: <80 m2 -> 2, <250 -> 3, <800 -> 4, else 6 floors, x 3.2 m)
  height_label    measured (Overture height) | estimated (from num_floors) | assumed (from footprint area)

Run (streams from Overture's public S3 bucket, nothing raw is kept on disk):
  .venv/bin/python data/corridor/fetch_buildings.py
If HTTPS fails with CERTIFICATE_VERIFY_FAILED on macOS:
  SSL_CERT_FILE=$(.venv/bin/python -m certifi) AWS_CA_BUNDLE=$(.venv/bin/python -m certifi) .venv/bin/python data/corridor/fetch_buildings.py
"""
import argparse
import json
import math
import time
from pathlib import Path

import shapely
from shapely.geometry import LineString, mapping
from shapely.ops import transform
from overturemaps import core

ROOT = Path(__file__).resolve().parents[2]
POINTS = ROOT / "data/corridor/corridor.json"
ROUTE = ROOT / "sim/corridor/route_points.json"
OUT = ROOT / "data/corridor/buildings"

HALF_M = 450      # half-width of the square around each corridor point
BAND_M = 150      # half-width of the band along the route
CHUNK = 8         # route points per band query box
FLOOR_M = 3.2
M_PER_DEG_LAT = 110_574


def m_per_deg_lon(lat):
    return 111_320 * math.cos(math.radians(lat))


def square(lat, lon, half_m):
    dx, dy = half_m / m_per_deg_lon(lat), half_m / M_PER_DEG_LAT
    return [round(lon - dx, 6), round(lat - dy, 6), round(lon + dx, 6), round(lat + dy, 6)]


def round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], 6), round(obj[1], 6)]
        return [round_coords(o) for o in obj]
    return obj


def assumed_floors(area_m2):
    if area_m2 < 80:
        return 2
    if area_m2 < 250:
        return 3
    if area_m2 < 800:
        return 4
    return 6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default=None, help="Overture release (default: latest)")
    ap.add_argument("--band-m", type=float, default=BAND_M)
    ap.add_argument("--half-m", type=float, default=HALF_M)
    args = ap.parse_args()

    points = json.loads(POINTS.read_text())["points"]
    route = json.loads(ROUTE.read_text())  # [[lat, lon], ...]
    lat0 = sum(p["lat"] for p in points) / len(points)
    kx, ky = m_per_deg_lon(lat0), M_PER_DEG_LAT

    def to_m(x, y, z=None):
        return (x * kx, y * ky)

    pts = {p["id"]: p for p in points}
    boxes = {p["id"]: square(p["lat"], p["lon"], args.half_m) for p in points}
    box_geoms = {pid: shapely.box(*b) for pid, b in boxes.items()}
    route_line_m = LineString([(lon * kx, lat * ky) for lat, lon in route])
    band_m = route_line_m.buffer(args.band_m)
    band_bbox = [v / k for v, k in zip(band_m.bounds, (kx, ky, kx, ky))]

    # Query boxes: the point squares, plus the route cut into chunks of CHUNK points padded by the band.
    queries = [tuple(b) for b in boxes.values()]
    for k in range(0, len(route) - 1, CHUNK):
        seg = route[k:k + CHUNK + 1]
        lat_c = sum(q[0] for q in seg) / len(seg)
        dx, dy = args.band_m / m_per_deg_lon(lat_c), args.band_m / M_PER_DEG_LAT
        queries.append((min(q[1] for q in seg) - dx, min(q[0] for q in seg) - dy,
                        max(q[1] for q in seg) + dx, max(q[0] for q in seg) + dy))
    print(f"{len(queries)} query boxes; streaming Overture buildings (STAC index) ...", flush=True)

    per_point = {pid: [] for pid in boxes}
    band = []
    seen_ids = set()
    stats = {"seen": 0, "kept": 0, "measured": 0, "estimated": 0, "assumed": 0}
    t0 = time.time()
    batches = (batch for q in queries
               for batch in core.record_batch_reader("building", bbox=q, release=args.release, stac=True))
    for batch in batches:
        cols = batch.to_pydict()
        n = batch.num_rows
        geoms = shapely.from_wkb(cols["geometry"])
        for i in range(n):
            if cols["id"][i] in seen_ids:
                continue
            seen_ids.add(cols["id"][i])
            stats["seen"] += 1
            if cols.get("is_underground", [None] * n)[i]:
                continue
            g = geoms[i]
            if g is None or g.is_empty:
                continue
            c = g.centroid
            in_boxes = [pid for pid, bg in box_geoms.items() if bg.contains(c)]
            cm = shapely.Point(c.x * kx, c.y * ky)
            if in_boxes:
                if len(in_boxes) > 1:
                    in_boxes.sort(key=lambda pid: (pts[pid]["lon"] - c.x) ** 2 * kx * kx + (pts[pid]["lat"] - c.y) ** 2 * ky * ky)
                target = per_point[in_boxes[0]]
            elif band_m.contains(cm):
                target = band
            else:
                continue
            height = cols.get("height", [None] * n)[i]
            floors = cols.get("num_floors", [None] * n)[i]
            if height is not None:
                label, render = "measured", height
            elif floors:
                height = floors * FLOOR_M
                label, render = "estimated", height
            else:
                area = transform(to_m, g).area
                label, render = "assumed", assumed_floors(area) * FLOOR_M
            stats[label] += 1
            stats["kept"] += 1
            target.append({
                "type": "Feature",
                "geometry": {"type": g.geom_type, "coordinates": round_coords(mapping(g)["coordinates"])},
                "properties": {
                    "id": cols["id"][i].replace("-", "")[:12],
                    "height": round(height, 1) if height is not None else None,
                    "num_floors": floors,
                    "render_height_m": round(render, 1),
                    "height_label": label,
                },
            })
        print(f"  {stats['seen']} scanned, {stats['kept']} kept ({time.time() - t0:.0f}s)", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    index = {}

    def write(name, feats, bbox, extra):
        path = OUT / f"{name}.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
        labels = {k: sum(1 for f in feats if f["properties"]["height_label"] == k) for k in ("measured", "estimated", "assumed")}
        index[name] = {"file": f"data/corridor/buildings/{name}.geojson", "count": len(feats), "bbox": bbox,
                       "size_kb": round(path.stat().st_size / 1024, 1), "height_labels": labels, **extra}

    for pid, feats in per_point.items():
        overlaps = [o for o in boxes if o != pid and box_geoms[o].intersects(box_geoms[pid])]
        write(pid, feats, boxes[pid], {"name": pts[pid]["name"], "half_width_m": args.half_m, "overlaps": overlaps})
    write("route_band", band, [round(v, 6) for v in band_bbox],
          {"name": f"Route band, {args.band_m:g} m either side, excluding point squares", "band_m": args.band_m})

    meta = {"source": "Overture Maps Foundation, buildings theme (release "
                      f"{args.release or core.get_latest_release()}); footprints from OpenStreetMap (ODbL-1.0), "
                      "Google Open Buildings (CC BY-4.0 / ODbL), Microsoft ML Buildings (ODbL) and others",
            "label": "footprints measured; heights measured where Overture has them, else estimated from floors, else assumed from footprint area",
            "fetched": time.strftime("%Y-%m-%d"), "dedup": "each building in exactly one file (nearest point where squares overlap)",
            "stats": stats}
    (OUT / "index.json").write_text(json.dumps({"_meta": meta, **index}, indent=1))
    total = sum(v["size_kb"] for v in index.values())
    print(json.dumps(stats), f"total {total / 1024:.1f} MB")


if __name__ == "__main__":
    main()
