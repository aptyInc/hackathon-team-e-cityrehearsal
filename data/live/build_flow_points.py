"""Choose where to ask TomTom's live Traffic Flow (flowSegmentData) about the corridor: writes data/live/flow_points.json.

Run once (needs the simulation's venv for sumolib):  python data/live/build_flow_points.py

Rules, in plain words:
  - Points lie on TomTom's own route geometry A->B (Traffic Stats job 10051304, data/tomtom/corridor/10051304.json),
    i.e. on the corridor's own carriageway, at least 150 m from either end of their leg (away from junction queues).
  - 2 points on legs of 1.3 km or more (when their clear spots are 400 m or more apart), else 1: 16 points (TomTom
    budget: at most ~24 requests a refresh).
  - A point can snap to the wrong road where another road runs alongside within 120 m in the same (or the opposite)
    direction: the road under a flyover, the flyover above a road, a service road. Such spots are avoided when the leg
    has a clear spot; the corridor's own two carriageways (the simulation's A->B and B->A routes) do not count.
    Legs without a clear spot (the corridor is on a flyover with the old road underneath) take the spot with the most
    room and are marked `risky`; spots TomTom answered wrongly once are in AVOID; GET /corridor/live_trip checks every answer (FRC0-3, the returned road follows the
    corridor A->B near the point) and drops a point that snapped elsewhere.
  - `on_flyover`: the simulation's route (which takes the flyovers, as TomTom's fastest legs show) is 4 m or more up
    there, so the corridor itself is on the structure.
"""
import csv, json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sim/corridor"))
import sumolib  # noqa: E402
import corridor_net as cn  # noqa: E402

ROUTE_JSON = ROOT / "data/tomtom/corridor/10051304.json"
LEGS_CSV = ROOT / "data/raw/corridor_legs_tomtom.csv"
OUT = Path(__file__).resolve().parent / "flow_points.json"
END_GAP_M, CLEAR_M, TWO_POINTS_M, MIN_APART_M = 150, 120, 1300, 400
# stretches whose TomTom answers failed GET /corridor/live_trip's check (lat, lon, radius m, why): no point there
AVOID = [(17.47973, 78.31750, 450, "10 Oct 2026: 78.3168-78.3181 snap to an FRC4 road (east end of the Nallagandla flyover)"),
         (17.405284, 78.461016, 100, "10 Oct 2026: snaps to a road that leaves the corridor (Lakdikapul)")]


def metres(a, b):
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((b[0] - a[0]) * 111320 * k, (b[1] - a[1]) * 110540)


def route_line():
    """TomTom's route as [(lon, lat)], cumulative metres, and the segment (frc, street) of each vertex."""
    segs = json.loads(ROUTE_JSON.read_text())["routes"][0]["segmentResults"]
    pts, seg = [], []
    for s in segs:
        for q in s["shape"]:
            p = (q["longitude"], q["latitude"])
            if not pts or pts[-1] != p:
                pts.append(p)
                seg.append((s["frc"], s.get("streetName")))
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + metres(a, b))
    return pts, cum, seg


def project(pts, cum, p):
    """(offset m, metres along) of p's closest point on the line."""
    best = None
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        k = math.cos(math.radians(a[1]))
        bx, by = (b[0] - a[0]) * 111320 * k, (b[1] - a[1]) * 110540
        px, py = (p[0] - a[0]) * 111320 * k, (p[1] - a[1]) * 110540
        L2 = bx * bx + by * by
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, (px * bx + py * by) / L2))
        d = math.hypot(px - t * bx, py - t * by)
        if best is None or d < best[0]:
            best = (d, cum[i] + t * math.sqrt(L2))
    return best


def at(pts, cum, dist):
    """(lon, lat), heading (radians, east = 0) and vertex index at `dist` metres along the line."""
    i = next((i for i in range(len(cum) - 1) if cum[i + 1] >= dist), len(cum) - 2)
    a, b = pts[i], pts[i + 1]
    w = (dist - cum[i]) / max(1e-6, cum[i + 1] - cum[i])
    k = math.cos(math.radians(a[1]))
    return (a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1])), math.atan2((b[1] - a[1]) * 110540, (b[0] - a[0]) * 111320 * k), i


def main():
    pts, cum, seg = route_line()
    corridor = json.loads((ROOT / "data/corridor/corridor.json").read_text())["points"]
    marks = [project(pts, cum, (p["lon"], p["lat"]))[1] for p in corridor]
    net = sumolib.net.readNet(str(NET))
    fwd, rev = cn.route(net), cn.route(net, reverse=True)
    own = {e.getID() for e in fwd + rev}
    out = []
    for k in range(len(corridor) - 1):
        a, b = marks[k], marks[k + 1]
        cands = []
        for f in [x / 40 for x in range(2, 39)]:
            d = a + f * (b - a)
            if d - a < END_GAP_M or b - d < END_GAP_M:
                continue
            (lon, lat), heading, i = at(pts, cum, d)
            if any(metres((lon, lat), (alon, alat)) < r for alat, alon, r, _ in AVOID):
                continue
            x, y = net.convertLonLat2XY(lon, lat)
            near_other = min((dd for e, dd in net.getNeighboringEdges(x, y, CLEAR_M)
                              if e.getFunction() != "internal" and e.allows("passenger") and e.getID() not in own
                              and (lambda diff: diff < math.radians(35) or diff > math.radians(145))(
                                  abs(math.remainder(cn._angle(e) - heading, 2 * math.pi)))), default=None)
            on_route = min(((dd, e) for e, dd in net.getNeighboringEdges(x, y, 25) if e in fwd), default=None, key=lambda t: t[0])
            on_fly = bool(on_route and max(abs(q[2]) for q in on_route[1].getShape3D()) >= 4)
            cands.append({"f": f, "along_m": round(d), "lon": round(lon, 6), "lat": round(lat, 6),
                          "heading_deg": round(math.degrees(heading)), "frc": f"FRC{seg[i][0]}", "street": seg[i][1],
                          "other_road_m": None if near_other is None else round(near_other), "on_flyover": on_fly})
        n = 2 if b - a >= TWO_POINTS_M else 1
        clear = [c for c in cands if c["other_road_m"] is None]
        pool = clear or sorted(cands, key=lambda c: -(c["other_road_m"] if c["other_road_m"] is not None else 1e9))[:3]
        if n == 2 and len(pool) >= 2:      # the two clear spots farthest apart
            pick = max(((p, q) for p in pool for q in pool if p["f"] < q["f"]), key=lambda pq: (pq[1]["f"] - pq[0]["f"]))
            if pick[1]["along_m"] - pick[0]["along_m"] < MIN_APART_M:     # both would read the same stretch: one is enough
                pick = [min(pick, key=lambda c: abs(c["f"] - 0.5))]
        else:                            # the clear spot nearest the middle of the leg
            pick = [min(pool, key=lambda c: abs(c["f"] - 0.5))]
        for c in pick:
            out.append({"id": f"p{k:02d}{'ab'[len([o for o in out if o['leg'] == k])]}", "leg": k,
                        "from_id": corridor[k]["id"], "to_id": corridor[k + 1]["id"], "lat": c["lat"], "lon": c["lon"],
                        "along_m": c["along_m"], "leg_from_m": round(a), "leg_to_m": round(b), "heading_deg": c["heading_deg"],
                        "route_frc": c["frc"], "street": c["street"], "on_flyover": c["on_flyover"],
                        "other_road_m": c["other_road_m"], "risky": c["other_road_m"] is not None})
    OUT.write_text(json.dumps({
        "note": "Where GET /corridor/live_trip asks TomTom's Traffic Flow Segment Data about the corridor (A->B). Written by "
                "data/live/build_flow_points.py; see its docstring for the rules. risky: another road runs within "
                f"{CLEAR_M} m (flyover/road underneath); every answer is checked before it is used.",
        "route": "TomTom Traffic Stats job 10051304 route geometry (data/tomtom/corridor/10051304.json)",
        "points": out}, indent=1))
    for p in out:
        print(p["id"], p["from_id"], "->", p["to_id"], p["lat"], p["lon"], "flyover" if p["on_flyover"] else "ground",
              f"RISKY other road {p['other_road_m']} m" if p["risky"] else "clear")
    print(len(out), "points ->", OUT)


NET = ROOT / "sim/corridor/corridor.net.xml"
if __name__ == "__main__":
    main()
