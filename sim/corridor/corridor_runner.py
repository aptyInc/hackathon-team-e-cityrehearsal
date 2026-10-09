"""Corridor simulation, Lingampally -> Lakdikapul: interventions in, C5 corridor result out.

Route: corridor_net.route(), over the flyovers through traffic really uses (Nallagandla, Gachibowli, Biodiversity
Level 1, Shaikpet, Tolichowki, Masab Tank), so the corridor meets signals only at j01, j02, j05, j08 and j09; the
junctions under the flyovers (j03, j04, j06, j07, j10, j11) carry no corridor through traffic. Leg times are split at
each corridor point projected onto the route (a flyover piece can run past a junction).

Traffic
  - Through traffic both ways along the corridor on fixed routes (end-to-end volume per direction: calibrated). At
    Lakdikapul (B) it disperses before the last ~130 m, a 5-into-2-lane give-way merge; only probe cars drive on.
  - Every arm of every junction carries traffic (junction_arms(), demand()), including the ground roads under the
    flyovers (j03, j04, j06, j07, j10/j11) and the corridor's own carriageway below them. Each arm gets TomTom Junction
    Analytics' volume (mean of the minutes collected within 06-23 h, `estimated`) x cross_scale, leaving by the exits in
    TomTom's measured turn shares (left/straight/right/U by angle, probe-weighted); with too few probes, or no TomTom
    at the junction (j01's and j05's TomTom areas are 1.3-2 km off the corridor; j11 has none), `assumed` volumes and
    splits. Corridor approaches are topped up only by the shortfall to TomTom's volume (traffic already arriving there
    is counted first: no double counting). Traffic turning onto the corridor drives JOIN_M on it, the rest EXTEND_M
    on its road. Side-road traffic enters INSERT_BACK_M up its road, so the junction's queue does not block it.
  - Drivers (VEHICLES, docs/driver-behaviour.md): seven vehicle types in the measured mix, Indian following gaps and
    reaction times (capacity x1.35 via headways), speeding, amber/red running, box blocking, giving way, side-street
    forcing; signals: free left, protected right phase, corridor >= 65% of the green (one approach at a time at big
    junctions is built but off: it gridlocked; corridor_net.BIG_JUNCTIONS). Out of scope (non-sublane model): lateral
    behaviour (filtering, weaving, side clearance) and creeping past the stop line (a viewer effect).
  - Probe cars every 30 s both ways record when they pass each corridor point: the trip time split by leg.

Noise: journey.total_s_se is the uncertainty of the trip time as an absolute number: the probe cars' spread in this
run combined with the run-to-run spread (the calibrated baseline with 3 other seeds, run_to_run_sd_s in
calibration.json). Comparing a variant with the baseline is a paired comparison: every run uses the same seed, the
same traffic (planned on the unchanged network) and the same netconvert rebuild (sim/templates/corridor.py rebuilds
every variant; the baseline gets a rebuild with no change), and each section is its own SUMO run, so a change only
moves the legs of the sections it touches. Drivers are imperfect (sigma, docs/driver-behaviour.md s3), so inside a
touched section the change also reshuffles the random draws: there the noise is the seed-to-seed spread of that
section (see SIGMA_NOTE for the measured size); a change is beyond noise when it exceeds about twice that spread x sqrt 2.

Running fast: the corridor runs as 6 sections (SECTIONS) at once, one SUMO each. A section is its legs plus 1 km of
road before them (traffic reaches the first junction in realistic platoons) and 300 m after; traffic entering it is the
corridor flow at that point. Trip time = sum of the legs. Each section starts full (fill flows), so 10 minutes of
warm-up and 15 minutes of probes are enough. A run takes about 30-60 s with 3 SUMO processes (CR_SIM_PARALLEL); frames (C1) cover 5 minutes.

Calibration (`calibrate()`, writes calibration.json), in plain words: TomTom measured how long each leg takes on
average (July 2026, 6 am-11 pm, `counted`) and, this evening, how long vehicles wait on the corridor's approaches at
the junctions it watches (Junction Analytics, `estimated`). We run the baseline, compare, adjust, a few times over:
  - leg too fast -> lower its speed (the leg's road speed stands in for what SUMO leaves out: buses stopping, parked
    vehicles, pedestrians, autos pulling in and out, "side friction").
  - leg too slow -> raise its speed; if it is already at 60 km/h the time is lost at the junction ending the leg, so
    the corridor gets more of that junction's green (up to 80%).
  - junction delay below TomTom's -> the corridor gets less green there (down to 35%), so more of the trip is spent
    waiting at junctions, as TomTom measures, and less as slow road. The target is TomTom's delay but at most the
    leg's time above free flow (50 km/h), since the delays are evening means and the leg times all-day means.
    Junctions the corridor flies over are left out of the delay targets; their volumes are still compared.
  - the network does not cope (vehicles stuck or unable to enter), or a leg is too slow even with 80% green -> all
    traffic is lowered 10% (to no less than 70% of the starting volumes).
The baseline then reproduces the measured trip, and interventions change it through what SUMO does model: junction
delays, queues, lanes and signals. Every knob is labelled in calibration.json and in the C5 result (inputs.sources).

Playback (for the 3D view)
  - frames (C1): a window of FRAMES_MAX_S at most, anywhere inside the measured period (the PROBE_SPAN after warm-up);
    run(frames_window=(from_s, to_s)). Driving is deterministic and recording frames only reads positions, so the
    journey and junction numbers do not depend on the window.
  - probe tracks: every probe car's whole trip (A->B and B->A), positions every PROBE_TRACK_S s from SUMO's FCD output
    (probe cars only), stitched across the sections; written to probes.json (probe_tracks()).

Hour of the day: with calibration_hourly.json (calibrate_hourly(), fitted to TomTom's hourly leg times when those rows
are in data/raw/corridor_legs_tomtom.csv), run(hour=h) applies that hour's volume scale (and, only where needed, a
speed-cap scale) on top of the all-day calibration. run(hour=h, day="2026-07-08") starts from the typical July hour and
adjusts it to that day-hour's TomTom trip time on demand (fit_day_hour(): 1-2 baseline runs, kept in
calibration_days.json and reused).
Now-cast: run(hour=h, day="live", live={...}) does the same against the live trip estimate (backend/app/live_trip.py:
TomTom live flow, legs and total; frozen per 10-minute bucket), kept in calibration_live.json per bucket and hour.

    python sim/corridor/corridor_runner.py calibrate          # writes sim/corridor/calibration.json
    python sim/corridor/corridor_runner.py calibrate_hourly [8 9 ...]   # writes sim/corridor/calibration_hourly.json
    python sim/corridor/corridor_runner.py fit_day 2026-07-08 18        # one day and hour (calibration_days.json)
    python sim/corridor/corridor_runner.py fit_live live.json [hour]    # a now-cast: hour's calibration to a live trip
    python sim/corridor/corridor_runner.py run [j07:flyover]  # prints the C5 result summary
"""
import csv, hashlib, heapq, json, math, os, re, shutil, statistics, subprocess, sys, time, uuid, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim/scripts"))
sys.path.insert(0, str(ROOT / "sim/templates"))
import corridor_net as cn  # noqa: E402
import sumolib  # noqa: E402
from sumolib import geomhelper  # noqa: E402

NET = HERE / "corridor.net.xml"
CALIBRATION = HERE / "calibration.json"
LEGS_CSV = ROOT / "data/raw/corridor_legs_tomtom.csv"
JA_CONFIG = ROOT / "data/tomtom/junction/corridor_junctions.json"
JA_LIVE = ROOT / "data/raw/tomtom_corridor_junction_live.csv"
JA_TURNS = ROOT / "data/raw/tomtom_corridor_turn_ratios.csv"
OUT = Path(os.environ.get("CR_SIM_OUT", ROOT / "sim/out")) / "corridor"
CORRIDOR_ID = "lingampally_lakdikapul"
TOMTOM_JOB = "10051304"           # July 2026, every day 06:00-23:00
THROUGH_VPH = {"fwd": 1500, "rev": 1500}   # end-to-end corridor traffic per direction (assumed; calibrated in calibration.json)
CROSS_SCALE = 0.6                 # share of TomTom's estimated cross-road volumes simulated (assumed; calibrated in calibration.json)
CROSS_VPH = 450                   # per cross-road approach at junctions without TomTom counts (assumed)
ASSUMED_SPLIT = {"fwd": 1 / 3, "rev": 1 / 3, "cross": 1 / 3}   # cross traffic: joins A->B, joins B->A, crosses (assumed)
MIN_TURN_PROBES = 10              # TomTom turn ratios are used for an approach once this many probe trips back them
JOIN_M = 1500                     # traffic that joins the corridor drives this far on it, then leaves (assumed; was 3 km:
                                  # with every arm loaded, joins from several junctions piled up beyond TomTom's volumes)
INSERT_BACK_M = 250               # cross traffic enters this far up its road, not at the stop line
FILL_STEP_M, FILL_SPEED = 2500, 6.0   # the corridor starts full: extra entry points every 2.5 km until traffic at 6 m/s arrives
MIX = {"two_wheeler": 0.47, "auto": 0.19, "car": 0.27, "bus": 0.04, "truck": 0.03}   # assumed (docs/driver-behaviour.md s2; VEHICLES)
MAX_KMH = 60                      # speed cap on the corridor before calibration
MAX_SHARE = 0.8                   # calibration gives the corridor at most this share of a junction's green
MIN_DEMAND = 0.7                  # calibration lowers traffic to no less than this share of the starting volumes
MIN_SHARE = 0.35                  # ... and gives the corridor at least this share of a junction's green at a big junction
MIN_SHARE_MAIN = 0.65             # ... and at a main x minor junction (docs/driver-behaviour.md s5: main road >= 65%)
STABLE_SHARE = {"j03": 0.7}       # ... except Gachibowli Circle: below 70% its roundabout fills up and locks in some runs


def min_share(jid):
    return STABLE_SHARE.get(jid, MIN_SHARE if jid in cn.BIG_JUNCTIONS else MIN_SHARE_MAIN)
FREE_KMH = 50                     # free-flow speed on the corridor's roads (assumed): a leg's time above it is delay
STEP = 0.5                        # s; the vehicle types' reaction times (tau 0.6-1.0 s) need steps no longer than this
SEED = 2                          # SUMO random seed: the same for the baseline and every variant (common random numbers)
SIGMA = 0                         # the probe cars only: they drive at the speed cap without imperfection (traffic: VEHICLES)
TELEPORT_S = 300                  # s a vehicle may stand still before SUMO lifts it out of a deadlock
PARALLEL = int(os.environ.get("CR_SIM_PARALLEL", "6"))   # SUMO processes at once per run (one per section at most)
WARMUP = 600                      # s before the first probe leaves
PROBE_EVERY, PROBE_SPAN = 30, 900   # one probe car each way every 30 s for 15 minutes (30 trips: noise is reported)
END = WARMUP + PROBE_SPAN + 3900  # long enough for the last probe to arrive (TomTom's trip: 58 min)
FRAMES = (WARMUP + 300, WARMUP + 600, 4)   # vehicle positions for the 3D view (C1): from, to, every N s (default window: 5 min, ~26 MB)
FRAMES_MAX_S = 600                # a frames window is at most 10 minutes (~50 MB) and lies inside WARMUP .. WARMUP + PROBE_SPAN
PROBE_TRACK_S = 5                 # probe car positions every N s for the whole trip (probes.json)
HOURLY = HERE / "calibration_hourly.json"
HOURS = range(6, 24)              # hour h = hh:00-hh+1:00: 06:00-07:00 .. 23:00-24:00
DAYS_FILE = OUT / "calibration_days.json"    # on-demand fits of single days and hours (fit_day_hour): a cache, not committed
LIVE_FILE = OUT / "calibration_live.json"    # now-cast fits per 10-minute bucket and hour (fit_day_hour, day "live"): a cache
LIVE_KEEP = 48                    # ... the newest this many are kept
HOUR_VOLUME = (0.5, 1.6)          # calibrate_hourly(): volume scale limits; beyond them it scales the speed caps
HOUR_CAP = (0.6, 2.2)             # ... within these limits
HOUR_MAX_KMH = 80                 # ... and no leg faster than this
SECTIONS = [("A_lingampally", "j01"), ("j01", "j02"), ("j02", "j04"), ("j04", "j07"), ("j07", "j09"), ("j09", "B_lakdikapul")]
LEAD_IN_M, TAIL_M = 1000, 300     # road simulated before / after each section's legs
C1_TYPES = {"two_wheeler", "car", "auto", "bus", "truck"}
JUNCTION_BLOCKER_S = int(os.environ.get("CR_JUNCTION_BLOCKER_S", "15"))   # s a vehicle waits behind one stuck inside the junction before moving past it (docs/driver-behaviour.md s6, assumed)
IMPATIENCE_S = int(os.environ.get("CR_IMPATIENCE_S", "30"))   # s of waiting after which a driver who must give way accepts much smaller gaps (s6, assumed)

# ---------- drivers (docs/driver-behaviour.md; labels as the doc: measured / estimated / assumed) ----------
# Non-sublane model (the sublane model was ~11x slower): vehicles keep to their lane in single file, so lateral
# behaviour (s4: position in the lane, side clearance, filtering, weaving) is out of scope.
CAPACITY = 1.35                   # s1 (assumed): real capacity = marked lanes x 1.35. Single file cannot fit 3 two-wheelers
                                  # across a lane, so the factor goes on the following headway instead; the network's
                                  # lanes are unchanged, so the intervention templates (flyover lanes, widening) see the
                                  # same roads
HEADWAY_FACTOR = 1.55             # every type's tau and minGap / this (tau not below STEP): the mix's saturation headway at
                                  # a 36 km/h discharge, tau + (length + minGap) / v, drops from 1.31 s (doc values) to
                                  # 0.97 s, i.e. capacity x1.35 (estimated; dividing by 1.35 itself gave only x1.23,
                                  # since vehicle lengths do not shrink)
# id, C1 type, share, vClass, length, width (m), top speed (km/h), accel, decel (m/s2), minGap (m), tau (s), sigma,
# speedFactor, jmDriveAfterRedTime (s; -1 = stops), jmIgnoreKeepClearTime (s)       (s2, s3, s7; all assumed)
VEHICLES = [
    ("two_wheeler_fast", "two_wheeler", 0.47 * 0.3, "motorcycle", 2.0, 0.8, 80, 3.0, 5.0, 0.6, 0.6, 0.6, "normc(1.25,0.1,1.05,1.5)", 2, 0),
    ("two_wheeler", "two_wheeler", 0.47 * 0.7, "motorcycle", 2.0, 0.8, 60, 2.5, 4.5, 0.8, 0.8, 0.5, "normc(1.0,0.1,0.8,1.2)", 1, 0),
    ("auto_fast", "auto", 0.19 * 0.5, "passenger", 2.6, 1.5, 60, 1.4, 4.0, 1.0, 0.8, 0.6, "normc(1.2,0.1,1.0,1.4)", 2, 0),
    ("auto", "auto", 0.19 * 0.5, "passenger", 2.6, 1.5, 50, 1.2, 4.0, 1.2, 0.9, 0.5, "normc(1.0,0.1,0.8,1.2)", 1, 0),
    ("car", "car", 0.27, "passenger", 4.3, 1.8, 80, 2.6, 4.5, 2.0, 1.0, 0.5, "normc(1.0,0.1,0.8,1.2)", 1, 5),
    ("bus", "bus", 0.04, "bus", 12.0, 2.5, 60, 1.0, 4.0, 2.5, 1.0, 0.5, "normc(1.0,0.1,0.8,1.2)", -1, 10),
    ("truck", "truck", 0.03, "truck", 7.5, 2.5, 60, 1.0, 4.0, 2.5, 1.0, 0.5, "normc(1.0,0.1,0.8,1.2)", -1, 10),
]
# the doc's prose says half of two-wheeler riders and 30% of autos are fast; its table says the reverse (30% / half):
# the table is followed, as the doc's own note says
SIGMA_SCALE = float(os.environ.get("CR_SIGMA_SCALE", "0.4"))   # x the doc's imperfection (0.5, fast 0.6): 0.2 / 0.24
SIGMA_NOTE = ("calibrated (spec 0.5): 0.2, fast riders 0.24. With the spec's 0.5 the Nanal Nagar section (j07-j09, near "
              "capacity) varied 278-404 s between seeds (sd ~70 s: a variant-vs-baseline comparison there would carry about "
              "+-3 min of noise). At 0.2, on the calibrated model (seeds 2-4): section sd 9-27 s, whole trip sd 50 s; paired "
              "variant-minus-baseline at the same seed, measured at seeds 2, 3, 4: flyover j08 -3.1 / -3.1 / -2.7 min (sd "
              "0.25 min), heavy rain +2.2 / +3.3 / +3.6 min (sd 0.7 min): a one-junction change is beyond noise above about "
              "+-0.5 min, a change to every leg (rain) above about +-1.5 min")
YELLOW_GO_S = 4                   # s7: nobody brakes for amber: whoever reaches the line in the 4 s amber goes (assumed)
RED_SPEED = 11.1                  # s7: red-runners keep their speed, up to 40 km/h (assumed)
GIVE_WAY_SPEED, GIVE_WAY_PROB = 1.5, 0.3   # s6: noses out in front of a priority vehicle crawling below 1.5 m/s, 30% per 0.5 s (assumed)
SIDE_SPEED, SIDE_PROB = 5.0, 0.5           # s6: side-street drivers force in while the main road is under 5 m/s, 50% per 0.5 s (estimated)


def c1_type(vtype):
    """C1 vehicle type of a simulation vType (two_wheeler_fast -> two_wheeler, car_side -> car, probe -> car)."""
    base = vtype.split("@")[0].removesuffix("_side").removesuffix("_fast")
    return base if base in C1_TYPES else "car"


def vtypes_xml():
    """The vehicle types (VEHICLES), each also as a side-street variant (<id>_side: forces its way into a slow main
    road, SIDE_SPEED/SIDE_PROB), and two distributions: "mix" (main roads) and "mix_side" (side streets)."""
    lines = []
    for side in (False, True):
        for vid, _, _, vcls, length, width, kmh, accel, decel, gap, tau, sigma, sf, red, keep in VEHICLES:
            jm = (f'jmDriveAfterYellowTime="{YELLOW_GO_S}" jmStoplineGap="0" jmIgnoreKeepClearTime="{keep}" '
                  f'jmIgnoreFoeSpeed="{SIDE_SPEED if side else GIVE_WAY_SPEED}" jmIgnoreFoeProb="{SIDE_PROB if side else GIVE_WAY_PROB}"'
                  + (f' jmDriveAfterRedTime="{red}" jmDriveRedSpeed="{RED_SPEED}"' if red >= 0 else ""))
            lines.append(f'    <vType id="{vid}{"_side" if side else ""}" vClass="{vcls}" length="{length}" width="{width}" '
                         f'maxSpeed="{kmh / 3.6:.2f}" accel="{accel}" decel="{decel}" minGap="{gap / HEADWAY_FACTOR:.2f}" '
                         f'tau="{max(STEP, tau / HEADWAY_FACTOR):.2f}" sigma="{sigma * SIGMA_SCALE:.3f}" speedFactor="{sf}" {jm}/>')
        names = [v[0] + ("_side" if side else "") for v in VEHICLES]
        lines.append(f'    <vTypeDistribution id="{"mix_side" if side else "mix"}" vTypes="{" ".join(names)}" '
                     f'probabilities="{" ".join(f"{v[2]:.4f}" for v in VEHICLES)}"/>')
    return "\n".join(lines)


# ---------- network ----------
def tomtom_legs():
    """TomTom July average per leg: [(from_id, to_id, distance_m, time_s, speed_kmh)] in corridor order (the all-day
    period of job TOMTOM_JOB; hourly rows, should the job carry them too, are left out)."""
    rows = [r for r in csv.DictReader(LEGS_CSV.open()) if r["job"] == TOMTOM_JOB and row_hour(r) is None]
    return [(r["from_id"], r["to_id"], float(r["distance_m"]), float(r["time_s"]), float(r["speed_kmh"])) for r in rows]


_PERIOD = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s*(?:\.\.|/|to|–|—)\s*(\d{4}-\d{2}-\d{2}))?[\sT]+(\d{1,2})(?:[:h.](\d{2}))?\s*(?:-|–|—|to)\s*(\d{1,2})(?:[:h.](\d{2}))?")


def row_hour(row):
    """The hour h when a TomTom row covers one hour of the day (hh:00-hh+1:00), else None. Tolerant of the period's
    format ("2026-07-01..2026-07-31 08:00-09:00", "... 8:00-9:00", "... 08-09", "2026-07-01/2026-07-31 T08:00-09:00")
    and of a separate `hour` column ("8", "08", "08:00", "08:00-09:00")."""
    h = (row.get("hour") or "").strip()
    if h:
        m = re.match(r"(\d{1,2})(?:[:h.]\d{2})?(?:\s*-\s*(\d{1,2}))?", h)
        if m and (m.group(2) is None or (int(m.group(2)) - int(m.group(1))) % 24 == 1):
            return int(m.group(1))
    m = _PERIOD.search(row.get("period") or "")
    if not m:
        return None
    h0, m0, h1, m1 = int(m.group(3)), int(m.group(4) or 0), int(m.group(5)), int(m.group(6) or 0)
    return h0 if m0 == 0 and m1 == 0 and (h1 - h0) % 24 == 1 else None


def row_dates(row):
    """(first, last) date of a TomTom row's period ('2026-07-01..2026-07-31 ...' -> both; a single date twice)."""
    d = re.findall(r"\d{4}-\d{2}-\d{2}", row.get("period") or "")
    return (d[0], d[1] if len(d) > 1 else d[0]) if d else (None, None)


def is_july(day):
    return day in (None, "", "july", "July")


def tomtom_hours(day=None):
    """TomTom's hourly rows in LEGS_CSV: {hour: {"period", "job", "legs": {(from_id, to_id): (distance_m, time_s,
    speed_kmh)}, "trip_total_s"}}. `day` None or "july": periods over several days (the typical July day; when an hour
    has several, the one covering July 2026 wins, else the one with the most legs); "2026-07-08": that day's periods
    only. {} while TomTom's hourly data is not in."""
    if not LEGS_CSV.exists():
        return {}
    by = {}
    for r in csv.DictReader(LEGS_CSV.open()):
        h = row_hour(r)
        if h is None:
            continue
        d0, d1 = row_dates(r)
        if (d0 != d1) if not is_july(day) else (d0 == d1):
            continue
        if not is_july(day) and d0 != day:
            continue
        p = by.setdefault(h, {}).setdefault((r.get("period", ""), r.get("job", "")), {"legs": {}, "trip_total_s": None})
        f = lambda k: float(r[k]) if (r.get(k) or "").strip() not in ("", "nan", "None") else None  # noqa: E731
        if r.get("from_id") and r.get("to_id") and f("time_s"):
            dist, t = f("distance_m"), f("time_s")
            speed = f("speed_kmh") or (dist / t * 3.6 if dist else None)
            p["legs"][(r["from_id"], r["to_id"])] = (dist, t, speed)
        if f("trip_total_s"):
            p["trip_total_s"] = f("trip_total_s")
    out = {}
    for h, periods in by.items():
        (period, job), p = max(periods.items(), key=lambda kv: ("2026-07" in kv[0][0], len(kv[1]["legs"])))
        out[h] = {"period": period, "job": job, **p}
    return out


def locate(net, path, reverse=False):
    """{corridor point id: (index of the path edge it lies on, metres into that edge, metres from the path's start)}.
    Points are projected onto the path (a flyover edge can run past a junction, so "nearest edge end" is not enough)."""
    pts = cn.CORRIDOR["points"][::-1] if reverse else cn.CORRIDOR["points"]
    cum = [0.0]
    for e in path:
        cum.append(cum[-1] + e.getLength())
    out, start = {pts[0]["id"]: (0, 0.0, 0.0)}, 0
    for p in pts[1:-1]:
        xy = net.convertLonLat2XY(p["lon"], p["lat"])
        dist = lambda k: geomhelper.distancePointToPolygon(xy, [q[:2] for q in path[k].getShape()], perpendicular=False)  # noqa: E731
        k = min(range(start, len(path)), key=dist)
        shape = [q[:2] for q in path[k].getShape()]
        frac = geomhelper.polygonOffsetWithMinimumDistanceToPoint(xy, shape, perpendicular=False) / max(1e-6, geomhelper.polyLength(shape))
        off = min(1.0, max(0.0, frac)) * path[k].getLength()
        out[p["id"]], start = (k, off, cum[k] + off), k
    out[pts[-1]["id"]] = (len(path) - 1, path[-1].getLength(), cum[-1])
    return out


def leg_of_edges(path, loc, reverse=False):
    """{edge id: leg index (A->B order)} by where each edge's middle lies between the corridor points."""
    pts = [p["id"] for p in (cn.CORRIDOR["points"][::-1] if reverse else cn.CORRIDOR["points"])]
    marks = [loc[p][2] for p in pts]
    n, out, done = len(pts) - 1, {}, 0.0
    for e in path:
        mid = done + e.getLength() / 2
        j = max(0, min(n - 1, sum(1 for m in marks[1:-1] if m <= mid)))
        out[e.getID()] = n - 1 - j if reverse else j
        done += e.getLength()
    return out


def calibrated_net(out: Path, caps=None, shares=None):
    """Copy of the network where each leg's corridor lanes run at the leg's calibrated speed (both directions; it
    replaces OSM's speed limit, which is mostly a road-type default and is 20 km/h on one stretch before Tolichowki),
    and the corridor's green share at each junction ({junction id: share}; others keep CORRIDOR_GREEN_SHARE)."""
    caps = caps if caps is not None else calibration()["cap_kmh"]
    net = sumolib.net.readNet(str(NET))
    fwd, rev = cn.route(net), cn.route(net, reverse=True)
    speed = {}
    for path, reverse in ((fwd, False), (rev, True)):
        for e, k in leg_of_edges(path, locate(net, path, reverse), reverse).items():
            speed[e] = caps[k] / 3.6
    tree = ET.parse(NET)
    for edge in tree.getroot().iter("edge"):
        v = speed.get(edge.get("id"))
        if v:
            for lane in edge.iter("lane"):
                lane.set("speed", f"{v:.2f}")
    tree.write(out)
    cn.signal_plans(out, shares or {})      # the plans of docs/driver-behaviour.md s5 with the calibrated green shares
    return out


# ---------- traffic ----------
def tomtom_volumes(field="volume_per_hour"):
    """TomTom Junction Analytics: mean of `field` (veh/h, or delay_s) per (junction_id, approach_id) over the minutes
    collected so far within the simulated day (HOURS, local time: the collector runs through the night too), and the
    time span used ('first .. last' minute)."""
    if not JA_LIVE.exists():
        return {}, None
    sums, times = {}, []
    for r in csv.DictReader(JA_LIVE.open()):
        if not (HOURS[0] <= int(r["time"][11:13]) <= HOURS[-1]):
            continue
        k = (r["junction_id"], r["approach_id"])
        n, v = sums.get(k, (0, 0.0))
        sums[k] = (n + 1, v + float(r.get(field) or 0))
        times.append(r["time"])
    return {k: v / n for k, (n, v) in sums.items()}, f"{min(times)[:16]} .. {max(times)[:16]}" if times else None


def tomtom_turns():
    """TomTom turn ratios, weighted by probe count: {(junction_id, approach name): {exit name: probes}} ({} when the
    collector has not written any)."""
    out = {}
    if JA_TURNS.exists():
        for r in csv.DictReader(JA_TURNS.open()):
            w = float(r["probes"] or 0) * float(r["ratio_percent"] or 0) / 100
            d = out.setdefault((r["junction_id"], r["approach"]), {})
            d[r["exit"]] = d.get(r["exit"], 0.0) + w
    return out


def _match(net, p1, p2, at_start=False, radius=50):
    """Network edge (cars allowed) near p2 (or p1 when `at_start`) heading from p1 to p2 ((lon, lat) points)."""
    x1, y1 = net.convertLonLat2XY(*p1[:2]); x2, y2 = net.convertLonLat2XY(*p2[:2])
    want, (x, y) = math.atan2(y2 - y1, x2 - x1), ((x1, y1) if at_start else (x2, y2))
    cands = [(e, d) for e, d in net.getNeighboringEdges(x, y, radius) if e.allows("passenger")
             and abs(math.remainder(cn._angle(e) - want, 2 * math.pi)) < math.radians(45)]
    return min(cands, key=lambda t: t[1])[0] if cands else None


def _leads_to(e, node_jid, corridor=(), limit=800.0):
    """(junction id, edge entering it): the first corridor junction node within `limit` m downstream of edge `e`,
    not driving along the corridor itself."""
    heap, seen, n = [(0.0, 0, e)], set(), 0
    while heap:
        d, _, x = heapq.heappop(heap)
        if x.getID() in seen:
            continue
        seen.add(x.getID())
        if x.getToNode().getID() in node_jid:
            return node_jid[x.getToNode().getID()], x
        for y in x.getOutgoing():
            if d + x.getLength() < limit and y.getFunction() != "internal" and y.getID() not in corridor:
                n += 1
                heapq.heappush(heap, (d + x.getLength(), n, y))
    return None, None


def _upstream(e, avoid, metres=INSERT_BACK_M):
    """Walk back from edge `e` along the same road (closest heading) for about `metres`, not onto `avoid` edges or
    through corridor junction nodes: cross traffic is inserted there, so its queue has room and insertion is not
    blocked by the junction's own queue."""
    done = 0.0
    while done < metres:
        node = e.getFromNode()
        if node.getID() in avoid:
            break
        ins = [x for x in node.getIncoming() if x.getID() not in avoid and x.allows("passenger") and x.getFromNode() != e.getToNode()]
        if not ins:
            break
        prev = min(ins, key=lambda x: abs(math.remainder(cn._angle(x) - cn._angle(e), 2 * math.pi)))
        if abs(math.remainder(cn._angle(prev) - cn._angle(e), 2 * math.pi)) > math.radians(60):
            break
        e = prev
        done += e.getLength()
    return e


def junction_counts(net, groups, fwd, rev):
    """TomTom Junction Analytics on the network: (cross, corridor, span).
    cross     {edge id: {"jid", "vph", "split": {"fwd", "rev", "cross"}, "road", "split_source"}}: each measured cross-road
              approach, matched to the network edge at the end of TomTom's approach with the same heading, and assigned to
              the corridor junction that edge leads to. TomTom's junction areas overlap (j08's covers j09), so an edge seen
              by two areas keeps the larger volume, once. split: where its traffic goes (TomTom turn ratios, else thirds).
    corridor  {junction id: {"fwd"/"rev": {"edge", "vph", "road"}}}: the busiest corridor approach each way (volume check).
    Approaches on roads the network does not have (lanes, colony roads) are left out."""
    vol, span = tomtom_volumes()
    delay, _ = tomtom_volumes("delay_s")
    if not vol or not JA_CONFIG.exists():
        return {}, {}, None
    turns = tomtom_turns()
    fwd_ids, rev_ids = {e.getID() for e in fwd}, {e.getID() for e in rev}
    node_jid = {n.getID(): jid for jid, g in groups.items() for n in g}
    cross, corridor = {}, {}
    for j in json.loads(JA_CONFIG.read_text())["junctions"]:
        jid = j["corridor_id"]
        path = ROOT / f"data/tomtom/junction/corridor/{jid}_definition.json"
        if not path.exists():
            continue
        model = json.loads(path.read_text())["junctionModel"]
        exit_kind = {}
        for x in model["exits"]:
            c = x["segmentedGeometry"]["coordinates"][0]
            e = _match(net, c[0], c[1], at_start=True)
            kind = "fwd" if e and e.getID() in fwd_ids else "rev" if e and e.getID() in rev_ids else "cross"
            exit_kind.setdefault(x["name"], []).append(kind)
        exit_kind = {k: max(set(v), key=v.count) for k, v in exit_kind.items()}
        for a in model["approaches"]:
            vph = vol.get((jid, str(a["id"])), 0)
            c = a["segmentedGeometry"]["coordinates"][-1]
            e = _match(net, c[-2], c[-1]) if vph >= 30 else None
            if e is None:
                continue
            if e.getID() in fwd_ids or e.getID() in rev_ids:
                tag = "fwd" if e.getID() in fwd_ids else "rev"
                if vph > corridor.setdefault(jid, {}).get(tag, {}).get("vph", 0):
                    corridor[jid][tag] = {"edge": e.getID(), "vph": round(vph), "road": a["name"],
                                          "delay_s": round(delay.get((jid, str(a["id"])), 0), 1)}
                continue
            if not groups.get(jid):     # the corridor passes over this junction (j04): its cross roads never meet it
                continue
            if e.getFromNode().getID() in node_jid:      # TomTom's approach ends inside the junction: the road into it
                ins = [x for x in e.getFromNode().getIncoming() if x.getID() not in fwd_ids | rev_ids
                       and x.getFromNode().getID() not in node_jid and x.allows("passenger")]
                e = min(ins, key=lambda x: abs(math.remainder(cn._angle(x) - cn._angle(e), 2 * math.pi))) if ins else None
            at, entry = _leads_to(e, node_jid, fwd_ids | rev_ids) if e else (None, None)
            if at != jid or entry.getID() in fwd_ids | rev_ids:     # only roads into this junction (areas overlap)
                continue
            probes = {}
            for name, w in turns.get((jid, a["name"]), {}).items():
                k = exit_kind.get(name, "cross")
                probes[k] = probes.get(k, 0.0) + w
            total = sum(probes.values())
            split = {k: probes.get(k, 0.0) / total for k in ("fwd", "rev", "cross")} if total >= MIN_TURN_PROBES else dict(ASSUMED_SPLIT)
            old = cross.get(e.getID())
            if old is None or vph > old["vph"]:
                cross[e.getID()] = {"jid": at, "vph": round(vph), "split": {k: round(v, 3) for k, v in split.items()}, "road": a["name"],
                                    "split_source": "estimated (TomTom turn ratios)" if total >= MIN_TURN_PROBES else "assumed"}
    return cross, corridor, span


# ---------- every arm of every junction ----------
GROUND_R, GROUND_R_WIDE = 70, 130     # m: a junction's nodes lie within this of its corridor point (wider if too few arms)
TOMTOM_NEAR_M = 400                   # a TomTom junction area centred further than this from the corridor junction is
                                      # another junction (j01's and j05's areas are 1.3-2 km away): not used there
ARM_MIN_VPH = 50                      # TomTom approaches below this are left out (colony lanes)
ARM_UPSTREAM_M = 400                  # a TomTom approach counts for an arm when it lies this far up the arm's road at most
ASSUMED_TURNS = {"L": 0.3, "S": 0.55, "R": 0.15, "U": 0.0}   # left (short turn, lefthand traffic), straight, right, U (assumed)
ASSUMED_VPH_PER_LANE, ASSUMED_VPH_MAX = 200, 450              # an arm without TomTom (assumed)
ARM_LANE_CAP = 800                    # veh/h per lane at most on a side arm (its share of a signal's green; assumed): where
                                      # the network has fewer lanes than the road (ISB Road: 1), TomTom's volume backs up
ARM_LANE_CAP_GIVE_WAY = 400           # ... where the arm gives way (no signal: under the Biodiversity flyover, Gachibowli Circle)
NOT_INSERTED_OK = 0.08                # calibration: up to this share of vehicles may wait to enter (side arms at capacity
                                      # queue beyond the modelled roads); more counts as the network not coping
EXTEND_M = 300                        # traffic leaving a junction drives this far on before it leaves the network
TOPUP_BACK_M = 400                    # corridor top-up traffic enters this far before the junction, in the moving stream
FLYOVER_SHARE = 0.81                  # through traffic that takes the flyover where there is one (docs/driver-behaviour.md s1, measured)


HEADING_M = 80                        # a road's direction into / out of a junction: over its last / first this many metres


def _poly_heading(pts, last=True, metres=HEADING_M):
    """Direction of a polyline (XY points) over its last (or first) `metres`: robust to the curve of a roundabout's
    entry or a slip road's last few metres."""
    pts = pts[::-1] if last else list(pts)
    done, far = 0.0, pts[1] if len(pts) > 1 else pts[0]
    for a, b in zip(pts, pts[1:]):
        far = b
        done += math.dist(a[:2], b[:2])
        if done >= metres:
            break
    (x0, y0), (x1, y1) = pts[0][:2], far[:2]
    return math.atan2(y0 - y1, x0 - x1) if last else math.atan2(y1 - y0, x1 - x0)


def _geo_heading(coords, net, last=True):
    return _poly_heading([net.convertLonLat2XY(c[0], c[1]) for c in coords], last)


def _end_heading(e, last=True):
    """Direction of edge `e` (and the road behind it / after it, up to HEADING_M) into (last) or out of a junction."""
    shape = list(e.getShape())
    x = e
    while sum(math.dist(a[:2], b[:2]) for a, b in zip(shape, shape[1:])) < HEADING_M:
        nxt = (x.getFromNode().getIncoming() if last else x.getToNode().getOutgoing())
        nxt = [y for y in nxt if (y.getToNode() != x.getFromNode() if not last else y.getFromNode() != x.getToNode())]
        if len(nxt) != 1:
            break
        x = nxt[0]
        shape = (list(x.getShape()) + shape[1:]) if last else (shape + list(x.getShape())[1:])
    return _poly_heading(shape, last)


def turn_classes(h_in, h_outs):
    """L / S / R / U for each heading out of a junction, given the heading into it (left = counter-clockwise; in
    lefthand traffic the short turn). Straight on: the exit closest to the approach's heading, if within 60 degrees
    (roads bend at junctions); U: turned back by more than 150 degrees."""
    d = [math.degrees(math.remainder(h - h_in, 2 * math.pi)) for h in h_outs]
    best = min(range(len(d)), key=lambda i: abs(d[i])) if d else None
    return ["S" if i == best and abs(x) < 60 else "U" if abs(x) > 150 else "L" if x > 0 else "R" for i, x in enumerate(d)]


def _inside(pt, ring):
    """Point in polygon (ray casting), XY."""
    x, y, hit = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def junction_clusters(net, base_groups, on_path):
    """{junction id: [node ids]}: where each corridor junction's arms meet. The signalised junctions the corridor
    crosses at ground level keep their signal's nodes (base_groups); elsewhere (under a flyover, or where side roads
    merge into and split off the corridor) the nodes within GROUND_R m of the junction that join 3+ roads, one of them
    not the corridor."""
    def nb(n):
        return {e.getFromNode().getID() for e in n.getIncoming()} | {e.getToNode().getID() for e in n.getOutgoing()}
    out = {}
    for p in cn.CORRIDOR["points"]:
        if p["kind"] != "junction":
            continue
        if base_groups.get(p["id"]):
            out[p["id"]] = sorted(base_groups[p["id"]])
            continue
        x, y = net.convertLonLat2XY(p["lon"], p["lat"])
        for r in (GROUND_R, GROUND_R_WIDE):
            ids = {n.getID() for n in net.getNodes() if math.dist(n.getCoord()[:2], (x, y)) < r and len(nb(n)) >= 3
                   and any(e.getID() not in on_path and e.allows("passenger") for e in n.getIncoming() + n.getOutgoing())}
            ins = [e for i in ids for e in net.getNode(i).getIncoming() if e.getFromNode().getID() not in ids and e.allows("passenger")]
            if len(ins) >= 2:
                break
        out[p["id"]] = sorted(ids)
    return out


def _road_chain(e, stop, metres=ARM_UPSTREAM_M):
    """{edge id: metres up the road from the arm's end}: arm `e` and the road behind it (closest heading), for matching
    TomTom's approaches to arms."""
    out, done = {e.getID(): 0.0}, 0.0
    while done < metres:
        node = e.getFromNode()
        if node.getID() in stop:
            break
        ins = [x for x in node.getIncoming() if x.allows("passenger") and x.getFromNode() != e.getToNode()]
        if not ins:
            break
        prev = min(ins, key=lambda x: abs(math.remainder(cn._angle(x) - cn._angle(e), 2 * math.pi)))
        if abs(math.remainder(cn._angle(prev) - cn._angle(e), 2 * math.pi)) > math.radians(60) or prev.getID() in out:
            break
        done += e.getLength()
        e = prev
        out[e.getID()] = done
    return out


def _tomtom_model(jid, net):
    """TomTom's junction model for `jid` when its area is at the corridor junction, else None."""
    path = ROOT / f"data/tomtom/junction/corridor/{jid}_definition.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    p = next(q for q in cn.CORRIDOR["points"] if q["id"] == jid)
    ring = ((d.get("rawJunction") or {}).get("geometry") or {}).get("coordinates") or [[]]
    pts = [net.convertLonLat2XY(c[0], c[1]) for c in ring[0]]
    if pts:
        cx, cy = sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
        here = net.convertLonLat2XY(p["lon"], p["lat"])
        if not _inside(here, pts) and math.dist((cx, cy), here) > TOMTOM_NEAR_M:
            return None
    return d["junctionModel"]


def junction_arms(net, base_groups):
    """Every arm of every corridor junction, on the base network: {junction id: {"nodes", "tomtom": "used"/"not at
    this junction"/"none", "arms": [{"edge", "road", "lanes", "vph" (TomTom mean, or assumed; None on a corridor arm
    without TomTom), "label", "turns": {"L","S","R","U"} shares, "turn_source", "probes", "corridor": "fwd"/"rev"/None,
    "signal": bool, "approaches": [TomTom approach names]}]}}.
    Volumes: TomTom Junction Analytics' mean per approach (estimated), matched to the arm whose road it lies on (end of
    the approach within ARM_UPSTREAM_M up the arm); several on one arm -> the largest (TomTom splits roads into
    overlapping approaches). Turns: TomTom's turn ratios turned into left/straight/right/U shares by the angle between
    the approach and each exit (probe-weighted), when MIN_TURN_PROBES probes back them; else ASSUMED_TURNS.
    fed_by_corridor: the corridor edge where TomTom measured an arm's traffic, when that is on the corridor before it
    splits into a flyover and the road below (j04): that volume is the flyover's and the road's together."""
    fwd, rev = cn.route(net), cn.route(net, reverse=True)
    F, R = {e.getID() for e in fwd}, {e.getID() for e in rev}
    clusters = junction_clusters(net, base_groups, F | R)
    all_nodes = {n for ids in clusters.values() for n in ids}
    vol, _ = tomtom_volumes()
    turns = tomtom_turns()
    out = {}
    for jid, ids in clusters.items():
        ids = set(ids)
        ins = sorted({e.getID(): e for i in ids for e in net.getNode(i).getIncoming()
                      if e.getFromNode().getID() not in ids and e.allows("passenger")}.values(), key=lambda e: e.getID())
        model = _tomtom_model(jid, net)
        status = "none" if not (ROOT / f"data/tomtom/junction/corridor/{jid}_definition.json").exists() else "used" if model else "not at this junction"
        chains = {e.getID(): _road_chain(e, all_nodes - ids) for e in ins}
        hits = {}
        for a in (model or {}).get("approaches", []):
            v = vol.get((jid, str(a["id"])), 0)
            c = a["segmentedGeometry"]["coordinates"][-1]
            if v < ARM_MIN_VPH or len(c) < 2:
                continue
            m = _match(net, c[-2], c[-1], radius=60)
            if m is None:
                continue
            if m.getFromNode().getID() in ids:        # TomTom's approach ends inside the junction: the arm feeding it
                cand = [e for e in ins if e.getToNode() == m.getFromNode()]
                arm = min(cand, key=lambda e: abs(math.remainder(cn._angle(e) - cn._angle(m), 2 * math.pi))) if cand else None
            else:
                cand = [(chains[e.getID()][m.getID()], e) for e in ins if m.getID() in chains[e.getID()]]
                arm = min(cand, key=lambda t: t[0])[1] if cand else None
            if arm is None:
                continue
            # turn class of each exit seen from this approach: an exit name can repeat, the one starting nearest the
            # approach's end is taken
            whole = [q for seg in a["segmentedGeometry"]["coordinates"] for q in seg]
            h_in, end = _geo_heading(whole, net), net.convertLonLat2XY(*c[-1][:2])
            heads = {}
            for x in model["exits"]:
                xc = [q for seg in x["segmentedGeometry"]["coordinates"] for q in seg]
                if len(xc) >= 2:
                    dd = math.dist(net.convertLonLat2XY(*xc[0][:2]), end)
                    if x["name"] not in heads or dd < heads[x["name"]][0]:
                        heads[x["name"]] = (dd, _geo_heading(xc, net, last=False))
            names = sorted(heads)
            kind = dict(zip(names, turn_classes(h_in, [heads[n][1] for n in names])))
            cls = {}
            for name, w in turns.get((jid, a["name"]), {}).items():
                if name in kind and w > 0:
                    cls[kind[name]] = cls.get(kind[name], 0.0) + w
            fed = m.getID() if m.getID() in F | R else None    # measured on the corridor before it splits (flyover / road below)
            hits.setdefault(arm.getID(), []).append((v, a["name"], cls, fed))
        arms = []
        for e in ins:
            corr = "fwd" if e.getID() in F else "rev" if e.getID() in R else None
            got = hits.get(e.getID(), [])
            probes = {}
            for _, _, cls, _ in got:
                for k, w in cls.items():
                    probes[k] = probes.get(k, 0.0) + w
            n = sum(probes.values())
            fed = None if corr else next((f for *_, f in got if f), None)
            if got:
                vph, label = max(v for v, *_ in got), "estimated (TomTom Junction Analytics)"
            elif corr:
                vph, label = None, "none (corridor traffic as it arrives)"
            else:
                vph, label = min(ASSUMED_VPH_MAX, ASSUMED_VPH_PER_LANE * e.getLaneNumber()), "assumed"
            arms.append({"edge": e.getID(), "road": e.getName() or (got[0][1] if got else ""), "lanes": e.getLaneNumber(),
                         "vph": round(vph) if vph is not None else None, "label": label,
                         "turns": {k: round(probes.get(k, 0.0) / n, 3) for k in "LSRU"} if n >= MIN_TURN_PROBES else dict(ASSUMED_TURNS),
                         "turn_source": f"estimated (TomTom turn ratios, {n:.0f} probes)" if n >= MIN_TURN_PROBES else "assumed",
                         "probes": round(n, 1), "corridor": corr, "signal": e.getToNode().getType() == "traffic_light",
                         "fed_by_corridor": fed, "approaches": sorted({name for _, name, *_ in got})})
        out[jid] = {"nodes": sorted(ids), "tomtom": status, "arms": arms}
    return out


def _extend(net, e, avoid, metres=EXTEND_M):
    """Edges after `e` along the same road (closest heading) for about `metres`, not onto `avoid` edges or nodes."""
    out, done = [], 0.0
    while done < metres:
        nxt = [x for x in e.getOutgoing() if x.allows("passenger") and x.getID() not in avoid and x.getToNode().getID() not in avoid
               and x.getToNode() != e.getFromNode()]
        if not nxt:
            break
        x = min(nxt, key=lambda x: abs(math.remainder(cn._angle(x) - cn._angle(e), 2 * math.pi)))
        if abs(math.remainder(cn._angle(x) - cn._angle(e), 2 * math.pi)) > math.radians(60):
            break
        out.append(x.getID())
        done += x.getLength()
        e = x
    return out


def demand(net, base_groups, volume_scale=1.0, through=None, cross_scale=CROSS_SCALE, tomtom=None, base=None, arms=None):
    """All traffic as flows [{"id", "route": [edge ids], "vph", "kind", "jid", "dir"}]: through traffic both ways along
    the corridor (fixed routes, `through` veh/h end to end), and traffic on every arm of every junction
    (junction_arms(): TomTom's volume x cross_scale where measured, else assumed), leaving by its exits in TomTom's
    measured turn shares (else assumed). Traffic that turns onto the corridor drives JOIN_M along it, then leaves; traffic
    leaving on another road drives EXTEND_M on, then leaves.
    No double counting on the corridor: at a corridor approach TomTom measures (at a junction, or on a flyover), the
    traffic already in the network that passes there (through traffic, traffic that joined upstream, earlier top-ups)
    is counted first, and only the shortfall to TomTom's volume x cross_scale is added ("top-up": local traffic that
    entered between junctions), 400 m before the junction. The top-up takes the approach's turning traffic first (the
    through traffic only goes straight on), the rest goes straight on. Approaches are taken in driving order.
    Demand is planned on the unchanged network `base` (so a variant carries exactly the baseline's demand; only routes
    change) and routed on `net`. `arms`: frozen junction_arms() (calibration.json), else measured now. Returns
    (flows, info)."""
    through = through or THROUGH_VPH
    base = base or net
    if arms is None:
        arms = (tomtom or {}).get("arms") or junction_arms(base, base_groups)
    groups = {j: [net.getNode(n) for n in ids if net.hasNode(n)] for j, ids in base_groups.items()}
    if tomtom:
        corridor, span = tomtom["corridor"], tomtom["span"]
    else:
        _, corridor, span = junction_counts(net, groups, cn.route(net), cn.route(net, reverse=True))
    plan = _plan(base, arms, corridor, through, cross_scale, volume_scale)
    flows, summary, ctx = _route_plan(net, plan, arms, through, volume_scale)
    return flows, {"cross": summary, "corridor": corridor, "tomtom_span": span, "paths": ctx["paths"], "pos": ctx["pos"],
                   "cut": ctx["cut"], "arms": arms}


def _ctx(net, arms):
    """Routing helpers for one network: corridor paths, where junctions lie on them, the Lakdikapul cut."""
    fwd, rev = cn.route(net), cn.route(net, reverse=True)
    paths = {"fwd": fwd, "rev": rev}
    pidx = {tag: {e.getID(): i for i, e in enumerate(p)} for tag, p in paths.items()}
    # Lakdikapul (B): traffic disperses at the junction there; past the last wide piece of road only the probe cars drive
    # on (the route's last ~130 m squeeze 5 lanes into 2 at a give-way merge, which jammed the whole last leg)
    end = len(fwd) - 2
    while end > 0 and fwd[end].getLaneNumber() < 3 and sum(e.getLength() for e in fwd[end:]) < 800:
        end -= 1
    cut = {"fwd": fwd[end].getID() if fwd[end].getLaneNumber() >= 3 else fwd[-1].getID(), "rev": rev[-1].getID()}
    return {"net": net, "paths": paths, "pidx": pidx, "on_path": set(pidx["fwd"]) | set(pidx["rev"]), "cut": cut,
            "pos": {"fwd": locate(net, fwd), "rev": locate(net, rev, reverse=True)},
            "all_nodes": {n for a in arms.values() for n in a["nodes"]}}


def _clip_dir(ctx, route, tag):
    c = ctx["cut"].get(tag)
    return route[:route.index(c) + 1] if c in route else route


def _tail(ctx, tag, edge_id):
    """Corridor edges after `edge_id` for JOIN_M (then the joining traffic leaves), clipped at Lakdikapul."""
    path, i = ctx["paths"][tag], ctx["pidx"][tag][edge_id]
    rest, done = [], 0.0
    for e in path[i + 1:]:
        if done >= JOIN_M:
            break
        rest.append(e.getID())
        done += e.getLength()
    return _clip_dir(ctx, rest, tag)


def _onward(ctx, o):
    """(route after exit edge `o`, direction): along the corridor for JOIN_M when `o` is on it or the road reaches it
    within 800 m (e.g. the road under a new flyover meets its landing), else EXTEND_M on along the road."""
    for tag in ("fwd", "rev"):
        if o.getID() in ctx["pidx"][tag]:
            return _tail(ctx, tag, o.getID()), tag
    ext = _extend(ctx["net"], o, ctx["all_nodes"] - {o.getToNode().getID()}, 800)
    for i, e in enumerate(ext):
        for tag in ("fwd", "rev"):
            if e in ctx["pidx"][tag]:
                return ext[:i + 1] + _tail(ctx, tag, e), tag
    done, keep = 0.0, []
    for e in ext:
        if done >= EXTEND_M:
            break
        keep.append(e)
        done += ctx["net"].getEdge(e).getLength()
    return keep, "cross"


def _exits(ctx, jid, arm, start, arms):
    """{turn class: [(route, direction)]}: from `start` through `arm` (edge objects) to each road leaving junction `jid`."""
    net, ids = ctx["net"], set(arms[jid]["nodes"])
    outs = {e.getID(): e for i in ids if net.hasNode(i) for e in net.getNode(i).getOutgoing()
            if e.getToNode().getID() not in ids and e.allows("passenger")}
    head = [arm]
    if start != arm:
        p, _ = net.getShortestPath(start, arm, vClass="passenger")
        head = p if p else [arm]
    found = []
    for o in sorted(outs.values(), key=lambda e: e.getID()):
        p, _ = net.getShortestPath(arm, o, vClass="passenger")
        if p and sum(x.getLength() for x in p[1:-1]) <= 600:      # through the junction, not round the block
            found.append((o, p))
    kinds = turn_classes(_end_heading(arm), [_end_heading(o, last=False) for o, _ in found])
    out = {}
    for (o, p), k in zip(found, kinds):
        if o.getToNode() == arm.getFromNode():
            k = "U"
        rest, tag = _onward(ctx, o)
        out.setdefault(k, []).append(([x.getID() for x in head] + [x.getID() for x in p[1:]] + rest, tag))
    return out


def _back(ctx, tag, edge_id, metres):
    """Corridor edge `metres` before `edge_id` (not past another junction's nodes; one with room to enter)."""
    path, i = ctx["paths"][tag], ctx["pidx"][tag][edge_id]
    k, done = i, 0.0
    while k > 0 and done < metres and path[k - 1].getToNode().getID() not in ctx["all_nodes"] - {path[i].getToNode().getID()}:
        k -= 1
        done += path[k].getLength()
    while k > 0 and path[k].getLength() < 20:
        k -= 1
    return path[k].getID()


def _plan(base, arms, corridor, through, cross_scale, volume_scale):
    """Demand on the unchanged network: [{"jid", "arm", "start", "kind": "arm"/"topup"/"flyover_topup", "vph": {class:
    veh/h}, "vtype", ...}], with the top-ups sized against the traffic already there (see demand())."""
    ctx = _ctx(base, arms)
    flows = [{"route": _clip_dir(ctx, [e.getID() for e in p], tag), "vph": through[tag] * volume_scale}
             for tag, p in ctx["paths"].items()]
    avoid = ctx["on_path"] | ctx["all_nodes"]
    plan = []

    def add(item):          # route the item on the base network so later top-ups see its traffic
        plan.append(item)
        for route, _, vph in _routes(ctx, item, arms):
            flows.append({"route": route, "vph": vph})

    for jid, a in arms.items():
        for arm in a["arms"]:
            if arm["corridor"] or arm["vph"] is None or not base.hasEdge(arm["edge"]):
                continue
            e = base.getEdge(arm["edge"])
            total = arm["vph"] * (cross_scale if arm["label"].startswith("estimated") else 1.0)
            total = min(total, (ARM_LANE_CAP if arm["signal"] else ARM_LANE_CAP_GIVE_WAY) * e.getLaneNumber()) * volume_scale
            turns, start, src = dict(arm["turns"]), _upstream(e, avoid).getID(), arm["turn_source"]
            fed = arm.get("fed_by_corridor")
            if fed and base.hasEdge(fed):
                # TomTom measured it on the corridor before the flyover splits off: below go the turning traffic and
                # the through traffic that does not take the flyover; it comes from the corridor (the flyover's
                # top-up below counts it as already there)
                turns["S"] = turns.get("S", 0.0) * (1 - FLYOVER_SHARE)
                total *= sum(turns.values())
                n = sum(turns.values()) or 1.0
                turns = {k: v / n for k, v in turns.items()}
                start, src = fed, src + f"; through traffic {FLYOVER_SHARE:.0%} on the flyover (measured)"
            add({"jid": jid, "arm": arm["edge"], "start": start, "kind": "arm", "road": arm["road"],
                 "vph": {k: total * s for k, s in turns.items()}, "vtype": "mix" if arm["signal"] or fed else "mix_side",
                 "label": arm["label"], "turn_source": src, "tomtom_vph": arm["vph"]})
    for tag in ("fwd", "rev"):          # corridor approaches TomTom measures, in driving order
        pts = []
        for jid, a in arms.items():
            for arm in a["arms"]:
                if arm["corridor"] == tag and arm["vph"] is not None and arm["edge"] in ctx["pidx"][tag]:
                    pts.append((ctx["pidx"][tag][arm["edge"]], jid, arm["edge"], arm["vph"], arm["turns"], "topup", arm["turn_source"], arm["road"]))
        armed = {p[2] for p in pts}
        for jid, d in corridor.items():
            m = d.get(tag)
            if m and m["edge"] in ctx["pidx"][tag] and m["edge"] not in armed and not any(p[1] == jid for p in pts):
                pts.append((ctx["pidx"][tag][m["edge"]], jid, m["edge"], m["vph"], {"S": 1.0}, "flyover_topup", "on the flyover: straight on", m["road"]))
        for _, jid, edge, vph, turns, kind, src, road in sorted(pts):
            target = vph * cross_scale * volume_scale
            arriving = sum(f["vph"] for f in flows if edge in f["route"])
            top = max(0.0, target - arriving)
            turning = target * (1 - turns.get("S", 0.0))
            if top >= turning:
                split = {k: target * s for k, s in turns.items() if k != "S"} | {"S": top - turning}
            else:
                split = {k: top * s / max(1e-9, 1 - turns.get("S", 0.0)) for k, s in turns.items() if k != "S"} | {"S": 0.0}
            if top < 1:
                plan.append({"jid": jid, "arm": edge, "start": edge, "kind": kind, "road": road, "vph": {}, "tag": tag,
                             "tomtom_vph": vph, "arriving_vph": round(arriving), "label": "estimated (TomTom Junction Analytics)",
                             "turn_source": src, "vtype": "mix"})
                continue
            add({"jid": jid, "arm": edge, "start": _back(ctx, tag, edge, TOPUP_BACK_M), "kind": kind, "road": road, "vph": split,
                 "tag": tag, "tomtom_vph": vph, "arriving_vph": round(arriving), "label": "estimated (TomTom Junction Analytics)",
                 "turn_source": src, "vtype": "mix"})
    return plan


def _routes(ctx, item, arms):
    """[(route, direction, veh/h)] of one plan item on ctx's network. A turn class with no road to take on this network
    gives its traffic to the other classes (in proportion)."""
    net = ctx["net"]
    if not item["vph"] or not net.hasEdge(item["arm"]):
        return []
    start = net.getEdge(item["start"]) if net.hasEdge(item["start"]) else net.getEdge(item["arm"])
    if item["kind"] == "flyover_topup":
        tag = item["tag"]
        if item["arm"] not in ctx["pidx"][tag] or start.getID() not in ctx["pidx"][tag]:
            return []
        i0, i1 = ctx["pidx"][tag][start.getID()], ctx["pidx"][tag][item["arm"]]
        route = [e.getID() for e in ctx["paths"][tag][i0:i1 + 1]] + _tail(ctx, tag, item["arm"])
        return [(_clip_dir(ctx, route, tag), tag, sum(item["vph"].values()))]
    ex = _exits(ctx, item["jid"], net.getEdge(item["arm"]), start, arms)
    vph = {k: v for k, v in item["vph"].items() if v > 0}
    have = {k: v for k, v in vph.items() if ex.get(k)}
    if not have:
        avail = [k for k in ("S", "L", "R") if ex.get(k)]
        have = {avail[0]: 0.0} if avail else {}
    total, kept = sum(vph.values()), sum(have.values())
    out = []
    for k, v in have.items():
        v = total * v / kept if kept > 0 else total
        for route, tag in ex[k]:
            out.append((route, tag, v / len(ex[k])))
    return out


def _route_plan(net, plan, arms, through, volume_scale):
    """Flows on `net` from the plan, and the per-junction summary (C5 inputs.cross_traffic)."""
    ctx = _ctx(net, arms)
    flows = [{"id": f"t{tag[0]}", "route": _clip_dir(ctx, [e.getID() for e in p], tag), "vph": through[tag] * volume_scale,
              "kind": "through", "dir": tag} for tag, p in ctx["paths"].items()]
    summary = {}
    for it in plan:
        rows = _routes(ctx, it, arms)
        for route, tag, v in rows:
            if v >= 1:      # side-road traffic enters INSERT_BACK_M before the end of its first road piece (some are km long)
                first = net.getEdge(route[0]).getLength()
                flows.append({"id": f"x{it['jid'][1:]}_{len(flows)}", "route": route, "vph": v, "kind": "cross", "jid": it["jid"],
                              "dir": tag, "vtype": it.get("vtype", "mix"),
                              "depart_pos": max(0.0, first - INSERT_BACK_M) if it["kind"] == "arm" and len(route) > 1 else 0.0})
        total = sum(v for _, _, v in rows)
        by = {k: round(sum(v for _, t, v in rows if t == k) / total, 3) if total else 0.0 for k in ("fwd", "rev", "cross")}
        s = summary.setdefault(it["jid"], {"approaches": 0, "vph": 0, "label": "assumed", "roads": [],
                                           "tomtom": arms.get(it["jid"], {}).get("tomtom", "none")})
        if total >= 1:
            s["approaches"] += 1
            s["vph"] += round(total)
        if it["label"].startswith("estimated"):
            s["label"] = "estimated"
        s["roads"].append({"road": it.get("road", ""), "edge": it["arm"], "enters_on": it["start"], "vph": round(total),
                           "label": "estimated" if it["label"].startswith("estimated") else "assumed", "split": by,
                           "split_source": it["turn_source"], "kind": {"arm": "arm", "topup": "corridor top-up",
                                                                      "flyover_topup": "corridor top-up (flyover)"}[it["kind"]],
                           "turns_vph": {k: round(v) for k, v in it["vph"].items()}, "tomtom_vph": it.get("tomtom_vph"),
                           **({"arriving_vph": it["arriving_vph"]} if "arriving_vph" in it else {})})
    for jid in arms:
        summary.setdefault(jid, {"approaches": 0, "vph": 0, "label": "none", "roads": [], "tomtom": arms[jid].get("tomtom", "none")})
    return flows, summary, ctx


# ---------- sections ----------
def sections(net, info):
    """The corridor split into SECTIONS that run in parallel. Each covers its legs plus LEAD_IN_M of road before (so
    traffic reaches its first junction in realistic platoons and queues) and TAIL_M after; [{"k", "legs", "fwd": (a, b),
    "rev": (a, b) path index ranges, "junctions" (simulated), "owned" (reported here), "end" s, "lon": (lo, hi)}]."""
    pts = [p["id"] for p in cn.CORRIDOR["points"]]
    lon = {p["id"]: p["lon"] for p in cn.CORRIDOR["points"]}
    tt = {(a, b): t for a, b, _, t, _ in tomtom_legs()}
    out = []
    for k, (p1, p2) in enumerate(SECTIONS):
        i1, i2 = pts.index(p1), pts.index(p2)
        sec = {"k": k, "legs": list(range(i1, i2)), "points": pts[i1:i2 + 1], "junctions": [], "owned": [],
               "lon": section_lon(k)}
        for tag, a, b in (("fwd", p1, p2), ("rev", p2, p1)):
            path, pos = info["paths"][tag], info["pos"][tag]
            cum = [0.0]
            for e in path:
                cum.append(cum[-1] + e.getLength())          # cum[i + 1]: distance to the end of path[i]
            da, db = pos[a][2], pos[b][2]
            start = 0 if da == 0 else next(i for i in range(len(path)) if cum[i + 1] > da - LEAD_IN_M)
            while start > 0 and path[start].getLength() < 50:   # vehicles enter the section on a piece with room
                start -= 1
            end = len(path) - 1 if db >= cum[-1] - 1e-6 else next((i for i in range(len(path)) if cum[i + 1] >= db + TAIL_M), len(path) - 1)
            sec[tag] = (start, end)
        sec["junctions"] = [p for p in pts[i1:i2 + 1] if p.startswith("j")]
        sec["owned"] = [p for p in pts[i1 + 1:i2 + 1] if p.startswith("j")]       # A->B approach fully inside
        sec["owned_rev"] = [p for p in pts[i1:i2] if p.startswith("j")]          # B->A approach fully inside
        sec["end"] = int(WARMUP + PROBE_SPAN + max(900, 1.6 * sum(tt[(pts[i], pts[i + 1])] for i in sec["legs"])) + 300)
        out.append(sec)
    return out


def section_routes(net, sec, flows, info, out: Path):
    """Routes file of one section: every flow cut to the section (the part of its route inside it), fill flows so the
    section starts full, and its probe cars. Vehicle ids start with the section number (probes: probe_fwd_<k>...)."""
    paths, k, end = info["paths"], sec["k"], sec["end"]
    slices = {tag: paths[tag][sec[tag][0]:sec[tag][1] + 1] for tag in ("fwd", "rev")}
    corridor = {e.getID() for p in paths.values() for e in p}
    inside = {e.getID() for s in slices.values() for e in s}
    inside |= {e for f in flows if f.get("jid") in sec["junctions"] for e in f["route"] if e not in corridor}
    stop = {"fwd": WARMUP + PROBE_SPAN + 60, "rev": end - 300}    # A->B traffic behind the last probe cannot affect it
    lines = ['<routes>', vtypes_xml(),
             # the probe car: a car with the car's junction behaviour, driving at the speed cap (speedFactor 1, sigma 0)
             f'    <vType id="probe" sigma="{SIGMA}" vClass="passenger" length="4.3" minGap="1.0" tau="0.8" maxSpeed="16.7" accel="2.6" decel="4.5" '
             f'speedFactor="1.0" color="1,1,1" jmDriveAfterYellowTime="{YELLOW_GO_S}" jmStoplineGap="0" jmIgnoreKeepClearTime="5" '
             f'jmIgnoreFoeSpeed="{GIVE_WAY_SPEED}" jmIgnoreFoeProb="{GIVE_WAY_PROB}" jmDriveAfterRedTime="1" jmDriveRedSpeed="{RED_SPEED}">'
             '<param key="has.vehroute.device" value="true"/><param key="has.fcd.device" value="true"/></vType>']
    entering = {"fwd": 0.0, "rev": 0.0}
    body = []
    for f in flows:
        route, run = f["route"], []
        for e in route:                     # the first stretch of the route inside the section
            if e in inside:
                run.append(e)
            elif run:
                break
        if not run or (f["kind"] == "cross" and f["jid"] not in sec["junctions"] and len(run) < 2):
            continue
        for tag in ("fwd", "rev"):
            if run[0] == slices[tag][0].getID():
                entering[tag] += f["vph"]
        tag = f.get("dir", "fwd")
        stop_at = stop.get(tag, end) if f["kind"] == "through" or (f["kind"] == "cross" and f["jid"] not in sec["junctions"]) else end
        pos = f' departPos="{f["depart_pos"]:.0f}"' if f.get("depart_pos") and run[0] == f["route"][0] else ""
        # traffic arriving from the previous section enters on the least busy lane (on its best lane, the many flows
        # entering the section on the same piece of road could not all get in)
        lane = "best" if run[0] == f["route"][0] else "free"
        body.append(f'    <flow id="{k}{f["id"]}" type="{f.get("vtype", "mix")}" begin="0" end="{stop_at}" vehsPerHour="{f["vph"]:.0f}" '
                    f'departLane="{lane}" departSpeed="max"{pos}><route edges="{" ".join(run)}"/></flow>')
    for tag, s in slices.items():
        # the section starts full: the traffic entering it also enters every FILL_STEP_M along the way until the
        # vehicles from the previous entry point get there (at FILL_SPEED), so probes meet steady traffic early on
        cum, last = 0.0, 0.0
        for i, e in enumerate(s[:-1]):
            cum += e.getLength()
            if cum - last >= FILL_STEP_M and cum < sum(x.getLength() for x in s) - 800 and s[i + 1].getLength() >= 50:   # room to enter
                body.append(f'    <flow id="{k}f{tag[0]}{i + 1}" type="mix" begin="0" end="{(cum - last) / FILL_SPEED:.0f}" '
                            f'vehsPerHour="{entering[tag]:.0f}" departLane="best" departSpeed="max">'
                            f'<route edges="{" ".join(_clip([x.getID() for x in s[i + 1:]], info["cut"][tag]))}"/></flow>')
                last = cum
    for tag, s in slices.items():     # last: SUMO ignores flows listed after a later-starting one (the B->A fill flows were)
        body.append(f'    <flow id="probe_{tag}_{k}" type="probe" begin="{WARMUP}" end="{WARMUP + PROBE_SPAN}" period="{PROBE_EVERY}" '
                    f'departLane="best" departSpeed="max"><route edges="{" ".join(x.getID() for x in s)}"/></flow>')
    out.write_text("\n".join(lines + body + ['</routes>']))
    return out


def _clip(route, last):
    """The route up to and including edge `last` (all of it when `last` is not on it)."""
    return route[:route.index(last) + 1] if last in route else route


def detectors(net, base_groups, sec, out: Path, count_edges=()):
    """A queue detector on the last 150 m of every lane approaching the section's junctions (whole run), and vehicle
    counts on `count_edges` (the corridor approaches TomTom measures) while the probes leave."""
    lines = ["<additional>"]
    for jid in sec["junctions"]:
        node_ids = base_groups.get(jid, [])
        nodes = [net.getNode(n) for n in node_ids if net.hasNode(n)]
        for e in {e for n in nodes for e in n.getIncoming() if e.getFromNode().getID() not in node_ids}:
            for lane in e.getLanes():
                L = lane.getLength()
                if L > 5:
                    lines.append(f'    <laneAreaDetector id="{jid}|{lane.getID()}" lane="{lane.getID()}" pos="{max(0, L - 150):.1f}" '
                                 f'endPos="{L - 0.5:.1f}" period="{sec["end"]}" file="e2_{sec["k"]}.xml"/>')
    edges = sorted({e for e in count_edges if net.hasEdge(e)})
    if edges:
        lines.append(f'    <edgeData id="counts" file="counts_{sec["k"]}.xml" begin="{WARMUP}" end="{WARMUP + PROBE_SPAN}" '
                     f'edges="{" ".join(edges)}"/>')
    lines.append("</additional>")
    out.write_text("\n".join(lines))
    return out


# ---------- run and measure ----------
def simulate(net, net_path: Path, sec, outdir: Path, frames=True, seed=SEED, window=None):
    """Run one section in SUMO. With `frames`, vehicle positions in the frames window ((from_s, to_s), default FRAMES;
    inside the section's own stretch) go to frames_<k>.jsonl through TraCI (SUMO's FCD output cannot stop at the
    window's end). Probe cars' positions every PROBE_TRACK_S s, whole run, go to fcd_<k>.xml (FCD device on the probe
    vType only). Neither changes the driving: the same seed gives the same numbers with any window or none."""
    k = sec["k"]
    lo_t, hi_t = window or FRAMES[:2]
    cmd = [sumolib.checkBinary("sumo"), "-n", str(net_path), "-r", str(outdir / f"routes_{k}.xml"), "-a", str(outdir / f"det_{k}.xml"),
           "--begin", "0", "--end", str(sec["end"]), "--seed", str(seed), "--step-length", str(STEP), "--no-step-log",
           "--log", str(outdir / f"sumo_{k}.log"), "--time-to-teleport", str(TELEPORT_S), "--ignore-route-errors",
           "--ignore-junction-blocker", str(JUNCTION_BLOCKER_S), "--time-to-impatience", str(IMPATIENCE_S),
           "--device.vehroute.probability", "0", "--vehroute-output", str(outdir / f"probes_{k}.xml"),
           "--vehroute-output.exit-times", "--statistic-output", str(outdir / f"stats_{k}.xml"),
           "--device.fcd.probability", "0", "--device.fcd.period", str(PROBE_TRACK_S), "--fcd-output", str(outdir / f"fcd_{k}.xml"),
           "--fcd-output.geo", "--fcd-output.attributes", "x,y,z,speed,lane,pos"]
    if not frames:
        subprocess.run(cmd, cwd=outdir, check=True, capture_output=True)
        return None
    import traci
    import traci.constants as tc
    label = f"cr_{outdir.name}_{k}_{uuid.uuid4().hex[:6]}"
    traci.start(cmd, label=label, stdout=subprocess.DEVNULL)
    conn, path = traci.getConnection(label), outdir / f"frames_{k}.jsonl"
    (bx0, by0), (bx1, by1) = net.getBBoxXY()
    centre = min(net.getNodes(), key=lambda n: math.dist(n.getCoord()[:2], ((bx0 + bx1) / 2, (by0 + by1) / 2))).getID()
    lo, hi = sec["lon"]
    try:
        conn.simulationStep(float(lo_t - FRAMES[2]))
        conn.junction.subscribeContext(centre, tc.CMD_GET_VEHICLE_VARIABLE, math.dist((bx0, by0), (bx1, by1)),
                                       [tc.VAR_POSITION3D, tc.VAR_ANGLE, tc.VAR_SPEED, tc.VAR_TYPE])
        with path.open("w") as f:
            t = lo_t
            while t <= hi_t:
                conn.simulationStep(float(t))
                vehicles = []
                for vid, v in (conn.junction.getContextSubscriptionResults(centre) or {}).items():
                    x, y, z = v[tc.VAR_POSITION3D]
                    lon, lat = net.convertXY2LonLat(x, y)
                    if lo <= lon < hi:
                        vehicles.append({"id": vid, "type": c1_type(v[tc.VAR_TYPE]),"lon": round(lon, 5), "lat": round(lat, 5),
                                         "z": round(z, 1) if abs(z) >= 0.05 else 0, "angle": round(v[tc.VAR_ANGLE]), "speed": round(v[tc.VAR_SPEED], 1)})
                f.write(json.dumps({"t": t, "vehicles": vehicles}, separators=(",", ":")) + "\n")
                t += FRAMES[2]
        conn.junction.unsubscribeContext(centre, tc.CMD_GET_VEHICLE_VARIABLE, 0)
        conn.simulationStep(float(sec["end"]))
    finally:
        conn.close()
    return path


def merge_frames(paths, out: Path):
    """One C1 frame per time step with the vehicles of every section."""
    files = [p.open() for p in paths]
    with out.open("w") as f:
        for lines in zip(*files):
            frames = [json.loads(l) for l in lines]
            f.write(json.dumps({"t": frames[0]["t"], "vehicles": [v for fr in frames for v in fr["vehicles"]]}, separators=(",", ":")) + "\n")
    for fh, p in zip(files, paths):
        fh.close(); p.unlink()
    return out


def probe_legs(sec, info, outdir: Path):
    """The section's legs (A->B direction): {leg index: (distance m, mean time s)} over its probe cars that got through."""
    path, pos = info["paths"]["fwd"], info["pos"]["fwd"]
    a, _ = sec["fwd"]
    per_probe = []
    for v in ET.parse(outdir / f"probes_{sec['k']}.xml").getroot().iter("vehicle"):
        if not v.get("id").startswith("probe_fwd") or v.get("arrival") is None:
            continue
        exits = [float(t) for t in v.find("route").get("exitTimes").split()]
        t = []
        for p in sec["points"]:          # time at the point: into the edge it lies on, plus its share of that edge
            k, off, cum = pos[p]
            if cum == 0:
                t.append(float(v.get("depart")))
                continue
            t_in = float(v.get("depart")) if k == a else exits[k - 1 - a]
            t.append(t_in + off / max(1e-6, path[k].getLength()) * (exits[k - a] - t_in))
        per_probe.append([y - x for x, y in zip(t, t[1:])])
        per_probe[-1].append(v.get("id").rsplit(".", 1)[1])     # probe number: same departure time in every section
    if not per_probe:
        raise RuntimeError(f"no probe car got through section {sec['points'][0]}-{sec['points'][-1]}; the network is gridlocked there")
    out = {}
    for n, leg in enumerate(sec["legs"]):
        p1, p2 = sec["points"][n], sec["points"][n + 1]
        dist = pos[p2][2] - pos[p1][2]
        times = [p[n] for p in per_probe]
        out[leg] = (dist, sum(times) / len(times), statistics.pstdev(times))
    return out, len(per_probe), {p[-1]: sum(p[:-1]) for p in per_probe}


def point_times(v, sec, tag, info):
    """{corridor point id: time the probe car passes it} for one probe vehicle (vehroute XML element) of section `sec`
    driving `tag` ("fwd"/"rev"): into the edge the point lies on, plus the point's share of that edge (as probe_legs())."""
    path, pos = info["paths"][tag], info["pos"][tag]
    a = sec[tag][0]
    depart = float(v.get("depart"))
    exits = [float(t) for t in v.find("route").get("exitTimes").split()]
    out = {}
    for p in sec["points"]:
        k, off, cum = pos[p]
        if cum == 0:
            out[p] = depart
            continue
        t_in = depart if k == a else exits[k - 1 - a]
        out[p] = t_in + off / max(1e-6, path[k].getLength()) * (exits[k - a] - t_in)
    return out


def thin_track(points, tol_m=2.0, tol_speed=1.5):
    """Drop the track points that interpolating by t between their neighbours reproduces (within tol_m and
    tol_speed m/s): standing still at a signal or cruising, a point every PROBE_TRACK_S s says nothing new. Points where
    the leg changes, and the first and last, are kept. Keeps probes.json small (~2 MB per run)."""
    if len(points) < 3:
        return points
    k = math.cos(math.radians(points[0]["lat"]))

    def fits(a, p, b):      # p as interpolated between a and b by time
        w = (p["t"] - a["t"]) / max(1e-9, b["t"] - a["t"])
        off = math.hypot((a["lon"] + w * (b["lon"] - a["lon"]) - p["lon"]) * 111320 * k, (a["lat"] + w * (b["lat"] - a["lat"]) - p["lat"]) * 110540)
        return off <= tol_m and abs(a["speed"] + w * (b["speed"] - a["speed"]) - p["speed"]) <= tol_speed \
            and abs(a["z"] + w * (b["z"] - a["z"]) - p["z"]) <= 0.5 and p["leg"] == a["leg"]

    out, skipped = [points[0]], []
    for p, b in zip(points[1:-1], points[2:]):
        if all(fits(out[-1], q, b) for q in skipped + [p]):     # every point dropped since the last kept one still fits
            skipped.append(p)
        else:
            out.append(p)
            skipped = []
    out.append(points[-1])
    return out


def probe_tracks(net, secs, info, outdir: Path, run_id=""):
    """Every probe car's whole trip, A->B and B->A, written to probes.json; returns (path, summary).
    The sections run side by side on one clock and probe N leaves each section's start at the same time, so a whole
    trip is stitched: section k's part (from its first corridor point to its last, in driving order) follows on where
    the previous section's part ended.
      clock      the times a corridor point is passed come from the vehroute exit times exactly as probe_legs() measures
                 the legs, so an A->B trip's total_s and legs_s are that probe's numbers in the journey (whose total_s is
                 the mean over the probes, per leg).
      positions  SUMO's FCD output for the probe cars every PROBE_TRACK_S s, cut where the car passes the section's
                 corridor points (distance along its route); the car's own times between those points are mapped
                 linearly onto the clock, so joints between sections meet exactly (a sample moves by a few s at most).
    segments[] give the C1 vehicle id per section (e.g. probe_fwd_3.12) and the same span on that section's own clock
    (sim_from_t/sim_to_t: the clock of the C1 frames), so the UI can find the car in the frames. Repeated positions
    while a car stands still are dropped (first and last kept): interpolate by t."""
    pts = [p["id"] for p in cn.CORRIDOR["points"]]
    geo = {}
    for tag in ("fwd", "rev"):
        path, cum = info["paths"][tag], [0.0]
        for e in path:
            cum.append(cum[-1] + e.getLength())
        geo[tag] = {"start": {e.getID(): (i, cum[i]) for i, e in enumerate(path)}, "path": path, "cum": cum}

    def where(tag, d):     # (lon, lat) on the route at distance d from its start
        g = geo[tag]
        i = next((i for i, c in enumerate(g["cum"][1:]) if c >= d), len(g["path"]) - 1)
        e = g["path"][i]
        shape = [q[:2] for q in e.getShape()]
        frac = min(1.0, max(0.0, (d - g["cum"][i]) / max(1e-6, e.getLength())))
        return net.convertXY2LonLat(*geomhelper.positionAtShapeOffset(shape, frac * geomhelper.polyLength(shape)))

    times = {}
    for sec in secs:
        f = outdir / f"probes_{sec['k']}.xml"
        if not f.exists():
            continue
        for v in ET.parse(f).getroot().iter("vehicle"):
            vid = v.get("id")
            if vid.startswith("probe_") and v.get("arrival") is not None:
                times[vid] = point_times(v, sec, vid.split("_")[1], info)
    samples = {}   # vehicle id -> [(t, lon, lat, z, speed, d: metres from the route's start)]
    for sec in secs:
        f = outdir / f"fcd_{sec['k']}.xml"
        if not f.exists():
            continue
        t, last = None, {}
        for ev, el in ET.iterparse(f, events=("start", "end")):
            if ev == "start" and el.tag == "timestep":
                t = float(el.get("time"))
            elif ev == "end" and el.tag == "vehicle":
                vid, lane = el.get("id"), el.get("lane") or ""
                g = geo[vid.split("_")[1]]
                hit = g["start"].get(lane.rsplit("_", 1)[0])
                if hit:
                    last[vid] = hit[0]
                    d = hit[1] + float(el.get("pos") or 0)
                elif lane.startswith(":") and vid in last:     # inside a junction: at the end of the edge it left
                    d = g["cum"][last[vid] + 1]
                else:
                    continue
                samples.setdefault(vid, []).append((t, float(el.get("x")), float(el.get("y")), float(el.get("z") or 0),
                                                    float(el.get("speed") or 0), d))
            elif ev == "end" and el.tag == "timestep":
                el.clear()

    def crossing(s, d):     # (time, z, speed) where the car passes distance d, linear between samples; None if not seen
        for a, b in zip(s, s[1:]):
            if a[5] < d <= b[5]:
                w = (d - a[5]) / max(1e-9, b[5] - a[5])
                return tuple(x + w * (y - x) for x, y in zip((a[0], a[3], a[4]), (b[0], b[3], b[4])))
        return None

    trips, incomplete = [], {"A->B": 0, "B->A": 0}
    for tag, direction in (("fwd", "A->B"), ("rev", "B->A")):
        order = secs if tag == "fwd" else secs[::-1]
        dist = {p: info["pos"][tag][p][2] for p in pts}
        for n in range(PROBE_SPAN // PROBE_EVERY):
            clock, depart, points, segments, legs = None, None, [], [], [0.0] * (len(pts) - 1)
            for sec in order:
                vid = f"probe_{tag}_{sec['k']}.{n}"
                c, s = times.get(vid), samples.get(vid)
                if not c or not s:
                    break
                route = sec["points"] if tag == "fwd" else sec["points"][::-1]
                t0, t1 = c[route[0]], c[route[-1]]
                d0, d1 = dist[route[0]], dist[route[-1]]
                if clock is None:
                    clock = depart = t0
                for p, q in zip(route, route[1:]):
                    legs[pts.index(p) if tag == "fwd" else pts.index(q)] += c[q] - c[p]
                ends = []
                for d, t_exit in ((d0, t0), (d1, t1)):
                    x = crossing(s, d)
                    near = min(s, key=lambda y: abs(y[5] - d))
                    ends.append((x[0], x[1], x[2]) if x else (t_exit, near[3], near[4]))
                (tau0, z0, v0), (tau1, z1, v1) = ends
                scale = (t1 - t0) / max(1e-6, tau1 - tau0)
                marks = [(dist[p], pts.index(p) if tag == "fwd" else pts.index(q)) for p, q in zip(route, route[1:])]
                leg_at = lambda d: next((k for m, k in reversed(marks) if d >= m), marks[0][1])  # noqa: E731
                end = clock + t1 - t0
                rows = [(clock, *where(tag, d0), z0, v0, d0)]
                rows += [y for y in ((clock + (x[0] - tau0) * scale, x[1], x[2], x[3], x[4], x[5]) for x in s if d0 < x[5] < d1)
                         if clock + 0.05 < y[0] < end - 0.05]
                rows.append((end, *where(tag, d1), z1, v1, d1))
                if points:
                    points.pop()           # section joint: the previous part's end point is this part's start
                for x in rows:
                    points.append({"t": round(x[0], 1), "lon": round(x[1], 6), "lat": round(x[2], 6),
                                   "z": round(x[3], 1) if abs(x[3]) >= 0.05 else 0, "speed": round(x[4], 1),
                                   "leg": leg_at(min(x[5], d1 - 1e-6))})
                segments.append({"section": sec["k"], "vehicle_id": vid, "from_id": route[0], "to_id": route[-1],
                                 "from_t": round(clock, 1), "to_t": round(clock + t1 - t0, 1),
                                 "sim_from_t": round(tau0, 1), "sim_to_t": round(tau1, 1)})
                clock += t1 - t0
            else:
                keep = thin_track(points)
                trips.append({"id": f"probe_{tag}.{n}", "direction": direction, "number": n, "depart_s": round(depart, 1),
                              "arrive_s": round(clock, 1), "total_s": round(clock - depart, 1),
                              "legs_s": [round(x, 1) for x in legs], "segments": segments, "points": keep})
                continue
            incomplete[direction] += 1
    path = outdir / "probes.json"
    meta = {"run_id": run_id, "step_s": PROBE_TRACK_S, "probe_every_s": PROBE_EVERY,
            "clock": "points[].t: seconds on the trip's clock (the first section's simulation clock; each later section's part "
                     "follows on where the previous one ended). segments[].sim_from_t/sim_to_t: the same part on that section's "
                     "own clock, the clock of the C1 frames, where the car is segments[].vehicle_id",
            "legs": [f"{a}->{b}" for a, b in zip(pts, pts[1:])], "leg": "points[].leg: index into legs (A->B order, both directions)",
            "incomplete": incomplete, "label": "SIMULATED: probe cars in the calibrated simulation (not measured trips)"}
    path.write_text(json.dumps({"meta": meta, "trips": trips}, separators=(",", ":")))
    for sec in secs:
        (outdir / f"fcd_{sec['k']}.xml").unlink(missing_ok=True)
    return path, {"trips": {d: sum(t["direction"] == d for t in trips) for d in ("A->B", "B->A")}, "incomplete": incomplete,
                  "points": sum(len(t["points"]) for t in trips), "bytes": path.stat().st_size}


def junction_stats(outdir: Path, secs, info):
    """Mean time lost and longest queue on each junction's approaches, and vehicles that entered them. Each approach is
    read from the section where it is simulated in full (not where its traffic is just entering the section)."""
    rev = {e.getID() for e in info["paths"]["rev"]}
    acc = {}
    for sec in secs:
        f = outdir / f"e2_{sec['k']}.xml"
        if not f.exists():
            continue
        for d in ET.parse(f).getroot().iter("interval"):
            jid, lane = d.get("id").split("|", 1)
            if jid not in (sec["owned_rev"] if lane.rsplit("_", 1)[0] in rev else sec["owned"]):
                continue
            a = acc.setdefault(jid, [0, 0.0, 0.0])
            n = int(d.get("nVehEntered", 0))
            a[0] += n
            a[1] += n * max(0.0, float(d.get("meanTimeLoss", 0)))
            a[2] = max(a[2], float(d.get("maxJamLengthInMeters", 0)))
    out = []
    for p in cn.CORRIDOR["points"]:
        if p["kind"] != "junction":
            continue
        n, loss, q = acc.get(p["id"], (0, 0, 0))
        out.append({"id": p["id"], "name": p["name"], "lat": p["lat"], "lon": p["lon"],
                    "avg_delay_s": round(loss / n, 1) if n else 0.0, "max_queue_m": round(q), "vehicles": n})
    return out


def approach_edges(info, base_groups):
    """{(junction id, "fwd"/"rev"): corridor edges from TomTom's measured approach up to the junction}."""
    out = {}
    for jid, dirs in info["corridor"].items():
        ids = set(base_groups.get(jid, []))
        if not ids:       # the corridor passes over this junction (j04): no approach delay of its own to compare
            continue
        for tag, m in dirs.items():
            path = [e.getID() for e in info["paths"][tag]]
            if m["edge"] not in path:
                continue
            i, run, done = path.index(m["edge"]), [], 0.0
            for e in info["paths"][tag][i:i + 15]:
                run.append(e.getID())
                done += e.getLength()
                if e.getToNode().getID() in ids:
                    if done < 1500:   # else TomTom's approach does not lead into this junction on the corridor (overlapping areas)
                        out[(jid, tag)] = run
                    break
    return out


def corridor_volumes(outdir: Path, secs, measured, approaches=None):
    """Simulated vs TomTom on the corridor approaches TomTom measures, while the probes leave: veh/h, and the delay
    (time lost per vehicle from TomTom's approach start up to the junction; TomTom: evening mean, estimated)."""
    rows = []
    for sec in secs:
        f = outdir / f"counts_{sec['k']}.xml"
        data = {e.get("id"): e for e in ET.parse(f).getroot().iter("edge")} if f.exists() else {}
        for jid in sec["junctions"]:
            for tag, m in sorted(measured.get(jid, {}).items()):
                if jid not in sec["owned" if tag == "fwd" else "owned_rev"]:
                    continue      # this direction's approach is read in the section that simulates it in full
                e = data.get(m["edge"])
                sim = (float(e.get("entered", 0)) + float(e.get("departed", 0))) * 3600 / PROBE_SPAN if e is not None else None
                lost = [float(data[x].get("timeLoss", 0)) / max(1.0, float(data[x].get("entered", 0)) + float(data[x].get("departed", 0)))
                        for x in (approaches or {}).get((jid, tag), []) if x in data]
                rows.append({"junction_id": jid, "direction": "A->B" if tag == "fwd" else "B->A", "road": m["road"], "edge": m["edge"],
                             "tomtom_vph": m["vph"], "sim_vph": round(sim) if sim is not None else None,
                             "tomtom_delay_s": m.get("delay_s"), "sim_delay_s": round(sum(lost), 1) if lost else None,
                             "label": "estimated"})
    return rows


def write_roads(net, outdir: Path):
    """GeoJSON of the corridor's main roads (for the map)."""
    feats = []
    for e in net.getEdges():
        if e.getFunction() == "internal" or not e.allows("passenger"):
            continue
        shape = e.getShape3D()   # z: flyovers and underpasses built by sim/templates/corridor.py are at +-6 m
        lifted = any(abs(z) > 0.5 for *_, z in shape)
        coords = [[round(v, 6) for v in net.convertXY2LonLat(x, y)] + ([round(z, 1)] if lifted else []) for x, y, z in shape]
        props = {"id": e.getID(), "lanes": e.getLaneNumber(), "name": e.getName()}
        kind = next((k for k in ("flyover", "underpass") if e.getID().startswith(k + "_")), None)
        if kind:   # the template's structure edges are named <kind>_<junction>_<fwd|rev>
            props.update(structure=kind, junction_id=e.getID().split("_")[1], flyover=kind == "flyover")
        feats.append({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}})
    path = outdir / "roads.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    return path


def calibration():
    """Calibrated knobs (calibration.json), or the assumed defaults before calibration."""
    c = json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else {}
    return {"cap_kmh": c.get("cap_kmh", [MAX_KMH] * (len(cn.CORRIDOR["points"]) - 1)),
            "through_vph": c.get("through_vph") if isinstance(c.get("through_vph"), dict) else dict(THROUGH_VPH),
            "cross_scale": c.get("cross_scale", CROSS_SCALE), "green_share": c.get("green_share", {}), "tomtom": c.get("tomtom"),
            "run_to_run_sd_s": c.get("run_to_run_sd_s", 0.0),
            "calibrated": bool(c)}


def frames_window(from_min=None, minutes=None):
    """(from_s, to_s) simulation seconds of the C1 frames: `from_min` minutes after warm-up (default 5), `minutes` long
    (default 5, 1..FRAMES_MAX_S/60), on the FRAMES step. The window must lie inside the measured period (PROBE_SPAN
    after WARMUP, while the probe cars leave and the corridor's traffic is steady). ValueError (plain words) if not."""
    total = PROBE_SPAN / 60
    from_min = (FRAMES[0] - WARMUP) / 60 if from_min is None else float(from_min)
    minutes = (FRAMES[1] - FRAMES[0]) / 60 if minutes is None else float(minutes)
    if not 1 <= minutes <= FRAMES_MAX_S / 60:
        raise ValueError(f"frames_minutes must be between 1 and {FRAMES_MAX_S // 60}, got {minutes:g}")
    if from_min < 0 or from_min + minutes > total + 1e-9:
        raise ValueError(f"the frames window must lie inside the {total:g} simulated minutes after warm-up: frames_from_min "
                         f"must be between 0 and {total - minutes:g} for {minutes:g} minutes of frames, got {from_min:g}")
    step = FRAMES[2]
    lo = WARMUP + round(from_min * 60 / step) * step
    return lo, min(WARMUP + PROBE_SPAN, lo + round(minutes * 60 / step) * step)


def frames_info(window):
    """C5 `frames_window`: what was recorded and the period a window can be chosen from (for the UI's slider)."""
    lo, hi = window
    return {"from_s": lo, "to_s": hi, "step_s": FRAMES[2], "from_min": round((lo - WARMUP) / 60, 2), "minutes": round((hi - lo) / 60, 2),
            "warmup_s": WARMUP, "sim_minutes_total": PROBE_SPAN // 60, "period_from_s": WARMUP, "period_to_s": WARMUP + PROBE_SPAN,
            "max_minutes": FRAMES_MAX_S // 60,
            "note": "frames t is simulation seconds; the window can start anywhere from 0 to sim_minutes_total - minutes after warm-up"}


# ---------- rain what-if ----------
RAIN_FACTORS = ROOT / "data/rain/rain_factors.json"
WEATHER = ("dry", "light_rain", "heavy_rain")
WEATHER_LABEL = "estimated (rain factors from TomTom hourly x Open-Meteo, July 2026)"


def weather_factors(weather, hour=None, day=None):
    """(speed factor per leg in corridor order, info) for run(weather=...): data/rain/rain_factors.json what_if.
    The calibration targets (July all-day, a typical July hour, or one day's hour) already contain some rain, so the
    factor is relative to that: reference time factor of the target / the setting's time factor. Only speed caps
    change (demand and signals do not). ValueError for an unknown setting or a factors file that does not fit."""
    if weather not in WEATHER:
        raise ValueError(f"weather must be one of {', '.join(WEATHER)}, got {weather!r}")
    f = json.loads(RAIN_FACTORS.read_text())
    wi = f["what_if"]
    ids = [p["id"] for p in cn.CORRIDOR["points"]]
    want = [f"{a}-{b}" for a, b in zip(ids, ids[1:])]
    if wi["legs"] != want:
        raise ValueError(f"rain_factors.json legs {wi['legs']} do not match the corridor's legs {want}")
    s = wi["settings"][weather]
    refs = wi["reference_time_factors"]
    if hour is None:
        ref, basis = refs["all_day"], "July 2026 all-day (06-23) rain mix"
    elif day == "live":
        ref, basis = [1.0] * len(want), "now (TomTom live); the rain right now is not known to the simulation, so taken as dry"
    elif is_july(day):
        ref, basis = refs["hour"][str(hour)], f"rain mix of July 2026 at {hour:02d}:00-{hour + 1:02d}:00"
    else:
        ref, basis = refs["day_hour"].get(f"{day} {hour:02d}", [1.0] * len(want)), f"the rain on {day} {hour:02d}:00-{hour + 1:02d}:00"
    factors = [round(r / t, 4) for r, t in zip(ref, s["per_leg_time_factor"])]
    return factors, {"weather": weather, "meaning": s["meaning"], "rain_class": s["class"], "label": WEATHER_LABEL,
                     "speed_factor_by_leg": dict(zip(want, factors)), "relative_to": basis,
                     "expected_trip_time_factor_vs_dry": s["trip_travel_time_factor"],
                     "expected_trip_time_factor_vs_dry_ci95": s["trip_travel_time_factor_ci95"],
                     "confidence": f.get("confidence"), "source": "data/rain/rain_factors.json (data/weather/analyse_weather_hourly.py)"}


def rain_on_structures(net_path, interventions, factors):
    """Flyover/underpass decks get the rain factor too (mean of the legs into and out of their junction): the template
    sets their speed itself, not from the speed caps, and a deck is not dry while the road under it is wet."""
    ids = [p["id"] for p in cn.CORRIDOR["points"]]
    prefixes = {}
    for iv in interventions:
        if iv["kind"] in ("flyover", "underpass") and iv["junction_id"] in ids[1:-1]:
            k = ids.index(iv["junction_id"])
            prefixes[f"{iv['kind']}_{iv['junction_id']}_"] = (factors[k - 1] + factors[k]) / 2
    if not prefixes:
        return []
    tree = ET.parse(net_path)
    done = []
    for edge in tree.getroot().iter("edge"):
        eid = edge.get("id") or ""
        f = next((v for p, v in prefixes.items() if eid.startswith(p)), None)    # the decks, not the ramp junctions
        if f is not None:
            for lane in edge.iter("lane"):
                lane.set("speed", f"{float(lane.get('speed')) * f:.2f}")
            done.append(eid)
    tree.write(net_path)
    return done


# ---------- water-logging hotspots (rain what-if, junction-specific) ----------
WATERLOGGING = ROOT / "data/weather/waterlogging_points.json"
WATERLOG_LABEL = "assumed, scaled by reported severity"
WATERLOG_SAMPLE_M = 25.0          # lane shapes are sampled this often when testing the distance to the junction


def waterlogging_points():
    """data/weather/waterlogging_points.json (reported water-logging hotspots per corridor junction) or None."""
    return json.loads(WATERLOGGING.read_text()) if WATERLOGGING.exists() else None


def waterlogging_factors(weather):
    """[(point, extra speed factor)] for this rain setting: the hotspots that flood in it (factor < 1), in corridor
    order. [] when dry, or without the data file. The table is the data file's (extra_speed_factor), so the API
    (/weather/factors) and the simulation always agree."""
    wl = waterlogging_points()
    if not wl or weather not in (wl.get("extra_speed_factor") or {}):
        return []
    table = wl["extra_speed_factor"][weather]
    order = {p["id"]: i for i, p in enumerate(cn.CORRIDOR["points"])}
    out = []
    for p in wl.get("points", []):
        f = float(table.get(p.get("severity"), 1.0))
        if p.get("junction_id") in order and f < 1.0:
            out.append((p, f))
    return sorted(out, key=lambda x: order[x[0]["junction_id"]])


def rain_at_hotspots(net_path, weather, base):
    """Extra speed cap on every lane within radius_m of a reported water-logging junction: the corridor approaching
    and leaving it, its cross arms and the junction's own internal lanes (not a flyover deck above it: that is why a
    flyover helps there). ON TOP of the per-leg rain factors (the measured average over a leg); the hotspot factor is
    the local extra the leg average hides. Returns the C5 inputs.weather fields (waterlogging, affected_junctions)."""
    hot = waterlogging_factors(weather)
    wl = waterlogging_points() or {}
    radius = float(wl.get("radius_m", 300))
    if not hot:
        return {"waterlogging": [], "affected_junctions": [], "waterlogging_radius_m": radius,
                "waterlogging_note": "no reported water-logging point floods in this rain setting" if wl else "data/weather/waterlogging_points.json missing"}
    pts = {p["id"]: p for p in cn.CORRIDOR["points"]}
    centres = {}
    for p, f in hot:
        c = pts[p["junction_id"]]
        centres[p["junction_id"]] = (base.convertLonLat2XY(c["lon"], c["lat"]), f)

    def samples(shape):
        """Points every WATERLOG_SAMPLE_M along the lane's shape (its vertices included)."""
        out = []
        for (x1, y1), (x2, y2) in zip(shape, shape[1:]):
            n = max(1, int(math.dist((x1, y1), (x2, y2)) / WATERLOG_SAMPLE_M))
            out += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]
        return out or shape

    tree = ET.parse(net_path)
    touched = {jid: 0 for jid in centres}
    for edge in tree.getroot().iter("edge"):
        eid = edge.get("id") or ""
        if eid.startswith("flyover_"):      # the deck is above the water (rain_on_structures slows it by the leg mean)
            continue
        for lane in edge.iter("lane"):
            shape = [tuple(map(float, xy.split(",")[:2])) for xy in (lane.get("shape") or "").split()]
            if not shape:
                continue
            pts_ = samples(shape)
            gap = {jid: min(math.dist(s, c) for s in pts_) for jid, (c, _) in centres.items()}
            hit = [jid for jid, d in gap.items() if d <= radius]
            if hit:
                jid = min(hit, key=lambda j: (centres[j][1], gap[j]))     # the strongest hotspot, then the nearest
                lane.set("speed", f"{float(lane.get('speed')) * centres[jid][1]:.2f}")
                touched[jid] += 1
    tree.write(net_path)
    label = f"{WATERLOG_LABEL} ({wl.get('label', 'reported (public sources), not measured by us')})"
    return {"waterlogging": [{"junction_id": p["junction_id"], "name": p.get("name") or pts[p["junction_id"]]["name"],
                              "junction_name": pts[p["junction_id"]]["name"], "severity": p.get("severity"),
                              "extra_speed_factor": f, "lanes_slowed": touched[p["junction_id"]], "label": label,
                              "what_reported": p.get("what_reported"), "sources": p.get("sources", [])} for p, f in hot],
            "affected_junctions": [pts[p["junction_id"]]["name"] for p, _ in hot],
            "waterlogging_radius_m": radius,
            "waterlogging_note": (f"{weather.replace('_', ' ')}: lanes within {radius:.0f} m of {len(hot)} reported water-logging "
                                  f"junction(s) get an extra speed cap (x{min(f for _, f in hot)}-x{max(f for _, f in hot)}, "
                                  f"{WATERLOG_LABEL}) on top of the per-stretch rain factor (the measured leg average). The stretch "
                                  "factor is the average rain effect over the whole leg; the junction factor is the local extra where "
                                  "water collects, which that average hides.")}


# ---------- hour of the day ----------
class HourlyUnavailable(LookupError):
    """run(hour=...) without calibration_hourly.json, or without that hour in it."""


def hourly_calibration():
    """calibration_hourly.json ({"hours": {"8": {"volume_scale", "cap_scale", "tomtom_total_s", ...}}}) or None."""
    return json.loads(HOURLY.read_text()) if HOURLY.exists() else None


def hour_label(hour):
    return f"July typical {hour:02d}:00-{hour + 1:02d}:00"


def day_label(day, hour):
    from datetime import date
    d = date.fromisoformat(day)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}, {hour:02d}:00-{hour + 1:02d}:00"


def day_fits():
    """calibration_days.json: on-demand fits of a single day and hour ({"fits": {"2026-07-08 18": {...}}})."""
    return (json.loads(DAYS_FILE.read_text()) if DAYS_FILE.exists() else {}).get("fits", {})


def _day_sig(base, d):
    """What a day-hour fit depends on: the July hour's calibration and that day-hour's TomTom numbers."""
    blob = json.dumps({"base": {k: base.get(k) for k in ("volume_scale", "cap_scale", "tomtom_total_s", "sim_total_s")},
                       "tomtom": [d.get("trip_total_s"), sorted((f"{a}->{b}", v[1]) for (a, b), v in d["legs"].items())]}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def live_tomtom(live):
    """The live trip estimate (backend live_trip: legs with distance_m and time_s on TomTom's route, total_s) as a
    tomtom_hours() entry, so fit_day_hour and trip_target treat it like a day-hour's TomTom rows."""
    legs = {(l["from_id"], l["to_id"]): (float(l["distance_m"]), float(l["time_s"]), float(l["distance_m"]) / float(l["time_s"]) * 3.6)
            for l in live["legs"]}
    return {"period": f"TomTom live trip estimate as of {live['as_of']}", "job": "TomTom live flow", "legs": legs,
            "trip_total_s": float(live["total_s"])}


def live_key(live, hour):
    return f"{live['bucket']} {hour:02d}"


def live_fits():
    """calibration_live.json: now-cast fits ({"fits": {"<bucket> <hour>": {...}}})."""
    return (json.loads(LIVE_FILE.read_text()) if LIVE_FILE.exists() else {}).get("fits", {})


def hour_settings(hour, day=None, live=None):
    """Scales for an hour of the day. `day` None or "july": the typical July hour (calibration_hourly.json). A single
    day ("2026-07-08"): its on-demand fit (calibration_days.json) when that fit still matches the July hour and
    TomTom's numbers, else {"needs_fit": True, "base": July hour, "tomtom": that day-hour's TomTom rows}.
    HourlyUnavailable (plain words) when the data is not there; ValueError for a bad hour or day."""
    if hour not in HOURS:
        raise ValueError(f"hour must be between {HOURS[0]} and {HOURS[-1]} (hh:00-hh+1:00), got {hour}")
    h = hourly_calibration()
    if h is None:
        raise HourlyUnavailable("hourly data not available yet: the corridor is calibrated to TomTom's all-day July average "
                                "(06:00-23:00) only; sim/corridor/calibration_hourly.json appears once TomTom's hourly "
                                "data is in and calibrate_hourly() has run")
    e = (h.get("hours") or {}).get(str(hour))
    if e is None:
        have = sorted(int(k) for k in (h.get("hours") or {}))
        raise HourlyUnavailable(f"hourly data not available yet for {hour:02d}:00-{hour + 1:02d}:00; calibrated hours: "
                                f"{', '.join(f'{k:02d}' for k in have) or 'none'}")
    if is_july(day):
        return dict(e, label=f"{hour_label(hour)} (TomTom hourly calibration)", window=hour_label(hour))
    if day == "live":
        if not live or not live.get("legs"):
            raise ValueError("day 'live' needs the live trip estimate (live={...}: GET /corridor/live_trip, frozen per bucket)")
        d = live_tomtom(live)
        sig = _day_sig(e, d)
        fit = live_fits().get(live_key(live, hour))
        if fit and fit.get("sig") == sig:
            return fit
        return {"needs_fit": True, "base": e, "tomtom": d, "sig": sig, "live": live}
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
        raise ValueError(f"day must be 'july' or a date like 2026-07-08, got {day!r}")
    d = tomtom_hours(day).get(hour)
    if d is None:
        raise HourlyUnavailable(f"TomTom data for {day} {hour:02d}:00-{hour + 1:02d}:00 not available yet")
    sig = _day_sig(e, d)
    fit = day_fits().get(f"{day} {hour:02d}")
    if fit and fit.get("sig") == sig:
        return fit
    return {"needs_fit": True, "base": e, "tomtom": d, "sig": sig}


def trip_target(d, legs, ref_total_s, ref_trip_s):
    """(TomTom's trip time over the simulated `legs`, basis) for one hour's TomTom rows `d` (tomtom_hours() entry):
    'leg speeds' when every leg is there (TomTom's speed per leg over the simulated leg lengths, as the all-day
    calibration), else 'trip total': `ref_total_s` (the reference's target over the simulated legs) scaled by TomTom's
    trip time for the hour over the reference's (`ref_trip_s`). (None, None) when neither is there."""
    if all(d["legs"].get((l["from_id"], l["to_id"]), (None, None, None))[2] for l in legs):
        return sum(l["distance_m"] / (d["legs"][(l["from_id"], l["to_id"])][2] / 3.6) for l in legs), "leg speeds"
    if d.get("trip_total_s") and ref_trip_s:
        return ref_total_s * d["trip_total_s"] / ref_trip_s, "trip total"
    return None, None


def allday_trip_s():
    """TomTom's all-day July trip time (job TOMTOM_JOB), the reference for hours given as trip totals only."""
    for r in csv.DictReader(LEGS_CSV.open()):
        if r["job"] == TOMTOM_JOB and row_hour(r) is None and (r.get("trip_total_s") or "").strip():
            return float(r["trip_total_s"])
    return sum(t for *_, t, _ in tomtom_legs())


def fit_day_hour(day, hour, cfg, final=None, tol=0.03):
    """Fit one day and hour on demand, from the typical July hour (cfg["base"]) to that day-hour's TomTom trip time:
    at most 2 baseline runs (first guess from the July hour's sensitivity of trip time to traffic, then a secant
    step); the volume scale moves, the speed caps instead when the July hour needed them too (light traffic at the
    volume floor, or a network that jams with more traffic) or the volume is at its limits. The fit is kept in
    calibration_days.json (reused while the July hour and TomTom's numbers are unchanged). `final`: {run_id, frames,
    frames_window} when the request itself is the baseline: the trial runs are then that request's run and the last
    one is returned. Returns (fit, result or None)."""
    base, d = cfg["base"], cfg["tomtom"]
    july = tomtom_hours().get(hour) or {}
    ref_trip = base.get("tomtom_trip_total_s") or july.get("trip_total_s")
    if d.get("trip_total_s") and ref_trip:
        t_est = base["tomtom_total_s"] * d["trip_total_s"] / ref_trip
    else:
        both = [(v[1], july["legs"][k][1]) for k, v in d["legs"].items() if k in july.get("legs", {}) and july["legs"][k][1]]
        t_est = base["tomtom_total_s"] * (sum(a for a, _ in both) / sum(b for _, b in both) if both else 1.0)
    v_h, cs_h, t_h = float(base["volume_scale"]), float(base.get("cap_scale", 1.0)), float(base["sim_total_s"])
    slope = float(base.get("slope_s_per_volume") or 600.0)       # s of trip per unit of volume scale near the July hour
    lv = cfg.get("live")
    if lv:       # a now-cast: the July hour adjusted to the live trip estimate
        labels = {"label": lv.get("label") or f"Now-cast {lv['as_of'][11:16]} IST (TomTom live; July {hour:02d}:00 calibration adjusted)",
                  "window": f"live {lv['as_of'][11:16]} IST (July {hour:02d}:00 calibration)", "period": d["period"], "job": d["job"],
                  "day": "live", "as_of": lv["as_of"], "bucket": lv["bucket"]}
    else:
        labels = {"label": f"{day_label(day, hour)} (July {hour:02d}:00 calibration adjusted to that day's TomTom trip time)",
                  "window": f"{day} {hour:02d}:00-{hour + 1:02d}:00", "period": d["period"], "job": d["job"], "day": day}

    def step(v, cs, t, target, slope):
        """Volume first (a day differs from the typical July hour by a moderate amount: at most 25% per step); the
        speed caps only when the volume is already at its limit in the direction needed."""
        nv = v + (target - t) / max(50.0, slope)
        lo, hi = max(HOUR_VOLUME[0], v / 1.25), min(HOUR_VOLUME[1], v * 1.25)
        if abs(cs_h - 1.0) > 1e-6 or (nv > v and v >= HOUR_VOLUME[1] - 1e-6) or (nv < v and v <= HOUR_VOLUME[0] + 1e-6):
            # the July hour already needed the caps (light traffic at the volume floor, or a network that jams with
            # more traffic): the day moves the caps too
            return v, round(min(HOUR_CAP[1], max(HOUR_CAP[0], cs * (t / target) ** 1.3)), 3)
        return round(min(hi, max(lo, nv)), 3), cs

    v, cs = step(v_h, cs_h, t_h, t_est, slope)
    trials, res = [], None
    for i in range(2):
        rid = final["run_id"] if final else f"calib_{day}_{hour:02d}_{i}"
        trial = {"volume_scale": v, "cap_scale": cs, "tomtom_total_s": round(t_est), **labels}
        res = run(hour=hour, day=day, hour_cfg=trial, run_id=rid, frames=bool(final and final.get("frames")),
                  frames_window=final.get("frames_window") if final else None, live=lv)
        if not final:
            shutil.rmtree(OUT / rid, ignore_errors=True)
        target, how = trip_target(d, res["journey"]["legs"], base["tomtom_total_s"], ref_trip)
        target = target or t_est
        t = res["journey"]["total_s"]
        trials.append({"volume_scale": v, "cap_scale": cs, "sim_total_s": t, "tomtom_total_s": round(target)})
        print(f"{labels['window']} trial {i}: sim {t / 60:.1f} min vs TomTom {target / 60:.1f} min | volume x{v} caps x{cs}", flush=True)
        if abs(t / target - 1) < tol or i == 1:
            break
        if abs(t - t_h) > 1 and abs(v - v_h) > 1e-6 and cs == cs_h:
            slope = max(50.0, (t - t_h) / (v - v_h))
        v, cs = step(v, cs, t, target, slope)
    fit = {"volume_scale": v, "cap_scale": cs, "tomtom_total_s": round(target), "sim_total_s": t, "ratio": round(t / target, 3),
           "within_tolerance": abs(t / target - 1) < tol, "target_basis": how or "trip total (estimated)",
           "tomtom_trip_total_s": d.get("trip_total_s"), "base_hour": {"hour": hour, "volume_scale": v_h, "cap_scale": cs_h,
                                                                       "tomtom_total_s": base["tomtom_total_s"]},
           "trials": trials, "sig": cfg["sig"], **labels, "fitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    path, skey = (LIVE_FILE, live_key(lv, hour)) if lv else (DAYS_FILE, f"{day} {hour:02d}")
    store = json.loads(path.read_text()) if path.exists() else {}
    store.setdefault("fits", {})[skey] = fit
    if lv:
        for old in sorted(store["fits"])[:-LIVE_KEEP]:
            store["fits"].pop(old)
        store["note"] = ("now-cast fits (fit_day_hour, day 'live'): the typical July hour's scales (calibration_hourly.json) "
                         "adjusted so the simulated trip matches the live trip estimate of that 10-minute bucket")
    else:
        store["note"] = ("on-demand fits of a single day and hour (fit_day_hour): the typical July hour's scales "
                         "(calibration_hourly.json) adjusted so the simulated trip matches that day-hour's TomTom trip time")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=1))
    if final:
        res["inputs"]["day_fit"] = {k: fit[k] for k in ("volume_scale", "cap_scale", "ratio", "within_tolerance", "target_basis", "trials")}
        if lv:
            res["inputs"]["live_fit"] = res["inputs"]["day_fit"]
        Path(res["roads_path"]).with_name("result.json").write_text(json.dumps(res, indent=1))
        return fit, res
    return fit, None


def run(interventions=(), volume_scale=1.0, run_id=None, frames=True, caps=None, label="July 2026 average, 6 am-11 pm", through=None,
        cross_scale=None, shares=None, seed=SEED, tomtom=None, frames_window=None, hour=None, day=None, hour_cfg=None, weather=None,
        live=None):
    """Simulate the corridor with `interventions` (C5 shape); return the C5 corridor result. `caps` (km/h per leg),
    `through` ({"fwd", "rev"} veh/h), `cross_scale` and `shares` ({junction id: corridor green share}) override the
    calibrated values (calibrate() uses them). `frames_window`: (from_s, to_s) of the C1 frames (default FRAMES; see
    frames_window()); it changes nothing else. `hour` (HOURS): that hour's scales on top of the all-day calibration;
    `day`: "july" (default, calibration_hourly.json) or a date like "2026-07-08" (fitted on demand from the July hour,
    fit_day_hour(), then reused). HourlyUnavailable without the data. `hour_cfg`: explicit scales (fit_day_hour).
    `weather` ("dry", "light_rain", "heavy_rain"; None = as calibrated): rain what-if, the estimated per-leg speed
    factors (weather_factors) on the speed caps after the hour's scales; nothing else changes.
    `live` (with day="live"): the live trip estimate frozen for a 10-minute bucket ({bucket, as_of, legs: [{from_id,
    to_id, distance_m, time_s}], total_s, ...}); the July hour is fitted to it on demand (calibration_live.json)."""
    window = tuple(frames_window) if frames_window else FRAMES[:2]
    run_id = run_id or "rc_" + uuid.uuid4().hex[:8]
    if hour is not None and hour_cfg is None:
        hour_cfg = hour_settings(hour, day, live)
        if hour_cfg.get("needs_fit"):
            plain = not interventions and volume_scale == 1.0 and all(x is None for x in (caps, through, cross_scale, shares, tomtom, weather)) and seed == SEED
            fit, res = fit_day_hour(day, hour, hour_cfg, {"run_id": run_id, "frames": frames, "frames_window": frames_window} if plain else None)
            if res is not None:
                return res
            hour_cfg = fit
    outdir = OUT / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cal = calibration()
    asked_scale = volume_scale
    if hour_cfg:
        volume_scale = volume_scale * float(hour_cfg.get("volume_scale", 1.0))
        caps = [min(HOUR_MAX_KMH, round(c * float(hour_cfg.get("cap_scale", 1.0)), 1)) for c in (caps if caps is not None else cal["cap_kmh"])]
        label = hour_cfg.get("label") or f"{hour_label(hour)} (TomTom hourly calibration)"
    rain = None
    if weather:      # after the hour's scales: the factor is relative to that hour's (or day-hour's) own rain
        rain_f, rain = weather_factors(weather, hour if hour_cfg else None, day)
        caps = [round(c * f, 2) for c, f in zip(caps if caps is not None else cal["cap_kmh"], rain_f)]
        label = f"{label} · {weather.replace('_', ' ')} (what-if)"
    through = through or cal["through_vph"]
    base = sumolib.net.readNet(str(NET))
    base_groups = {j: [n.getID() for n in g] for j, g in cn.junction_groups(base).items() if g}
    net_path = calibrated_net(outdir / "corridor.net.xml", caps if caps is not None else cal["cap_kmh"],
                              shares if shares is not None else cal["green_share"])
    warnings = []
    variant = outdir / "variant.net.xml"
    if interventions:
        import corridor as templates   # sim/templates/corridor.py (interventions)
        warnings += templates.apply(net_path, variant, list(interventions))
        if rain:
            rain["structures_slowed"] = rain_on_structures(variant, list(interventions), rain_f)
    else:   # the baseline goes through the same netconvert rebuild as every variant, so they differ only by the change
        cn.rebuild(net_path, variant, lambda prefix: None)
    if rain:     # reported water-logging junctions: extra local cap on top of the leg factors (rain_at_hotspots)
        rain.update(rain_at_hotspots(variant, weather, base))
    net_path = variant
    net = sumolib.net.readNet(str(net_path))
    flows, info = demand(net, base_groups, volume_scale, through, cross_scale if cross_scale is not None else cal["cross_scale"],
                         tomtom or cal["tomtom"], base=base)
    secs = sections(net, info)
    approaches = approach_edges(info, base_groups)
    count_edges = [m["edge"] for d in info["corridor"].values() for m in d.values()] + [e for v in approaches.values() for e in v]
    clusters = {j: a["nodes"] for j, a in info["arms"].items()} | base_groups     # every junction's ground nodes (stats)
    for sec in secs:
        section_routes(net, sec, flows, info, outdir / f"routes_{sec['k']}.xml")
        detectors(net, clusters, sec, outdir / f"det_{sec['k']}.xml", count_edges)
    with ThreadPoolExecutor(min(len(secs), PARALLEL)) as pool:
        frame_files = list(pool.map(lambda s: simulate(net, net_path, s, outdir, frames, seed, window), secs))
    frames_path = merge_frames(frame_files, outdir / "frames.jsonl") if frames else None
    tracks_path, tracks = probe_tracks(net, secs, info, outdir, run_id)
    legs, n_probes, trips = {}, [], {}
    for sec in secs:
        got, n, per = probe_legs(sec, info, outdir)
        legs.update(got); n_probes.append(n)
        for i, t in per.items():
            trips.setdefault(i, []).append(t)
    trips = [sum(t) for t in trips.values() if len(t) == len(secs)]    # whole trips: probe i's legs in every section
    sd = statistics.pstdev(trips) if len(trips) > 1 else None
    tt = tomtom_legs()
    pts = cn.CORRIDOR["points"]
    out_legs = []
    for k, (_, _, _, _, tt_kmh) in enumerate(tt):
        dist, secs_, leg_sd = legs[k]
        out_legs.append({"from_id": pts[k]["id"], "to_id": pts[k + 1]["id"], "from_name": pts[k]["name"], "to_name": pts[k + 1]["name"],
                         "distance_m": round(dist), "time_s": round(secs_), "speed_kmh": round(dist / secs_ * 3.6, 1) if secs_ else None,
                         # TomTom's measured speed on this leg, over the simulated leg's length
                         "tomtom_time_s": round(dist / (tt_kmh / 3.6)),
                         "time_s_sd": round(leg_sd, 1)})       # spread between the probe cars
    if hour_cfg:     # TomTom's times for that hour: its own leg speeds when the hourly rows have every leg, else scaled
        ids = [p["id"] for p in pts]
        hl = live_tomtom(live)["legs"] if day == "live" and live else tomtom_hours(day).get(hour, {}).get("legs", {})
        if all(hl.get((a, b), (None, None, None))[2] for a, b in zip(ids, ids[1:])):
            for l in out_legs:
                l["tomtom_time_s"] = round(l["distance_m"] / (hl[(l["from_id"], l["to_id"])][2] / 3.6))
        elif hour_cfg.get("tomtom_total_s"):
            f = float(hour_cfg["tomtom_total_s"]) / max(1, sum(l["tomtom_time_s"] for l in out_legs))
            for l in out_legs:
                l["tomtom_time_s"] = round(l["tomtom_time_s"] * f)
    teleports = loaded = waiting = 0
    for sec in secs:
        stats = ET.parse(outdir / f"stats_{sec['k']}.xml").getroot()
        teleports += int(stats.find("teleports").get("total"))
        loaded += int(stats.find("vehicles").get("loaded")); waiting += int(stats.find("vehicles").get("waiting"))
    if teleports > 0.01 * loaded:
        warnings.append(f"{teleports} vehicles were stuck for 5 minutes and skipped ahead (gridlock somewhere on the network)")
    if waiting > NOT_INSERTED_OK * loaded:
        warnings.append(f"{waiting} vehicles could not enter the network by the end (queues back up beyond the modelled roads)")
    if min(n_probes) < PROBE_SPAN // PROBE_EVERY:
        warnings.append(f"in some sections only {min(n_probes)} of {PROBE_SPAN // PROBE_EVERY} probe cars got through in time")
    kinds = {i["kind"] for i in interventions}
    cross = info["cross"]
    measured = any(v["label"] == "estimated" for v in cross.values())
    result = {
        "run_id": run_id, "variant_id": "baseline" if not interventions else "+".join(f"{i['kind']}_{i['junction_id']}" for i in interventions),
        "corridor_id": CORRIDOR_ID,
        "time": {"window": (hour_cfg.get("window") or hour_label(hour)) if hour_cfg else "2026-07", "minutes": PROBE_SPAN // 60, "label": label}
                | ({"weather": weather} if weather else {})
                | ({"hour": hour, "day": "july" if is_july(day) else day,
                    "data_label": ("calibrated to TomTom's hourly leg times (" if is_july(day) else "July hour adjusted to TomTom's trip time for ")
                    + str(hour_cfg.get("period", "July 2026")) + (")" if is_july(day) else "")} if hour_cfg else {})
                | ({"as_of": live["as_of"], "bucket": live["bucket"],
                    "data_label": f"July {hour:02d}:00 calibration adjusted to the live trip estimate (TomTom live flow, as of "
                                  f"{live['as_of']}; estimated)"} if hour_cfg and day == "live" and live else {}),
        "interventions": list(interventions),
        "journey": {"total_s": sum(l["time_s"] for l in out_legs), "distance_m": sum(l["distance_m"] for l in out_legs),
                    "tomtom_total_s": sum(l["tomtom_time_s"] for l in out_legs), "legs": out_legs,
                    # noise: spread of whole-trip times between probe cars, and the uncertainty of the mean (total_s)
                    "total_s_sd": round(sd, 1) if sd is not None else None,
                    # uncertainty of total_s: the probes' spread in this run and the run-to-run spread (other seeds,
                    # measured at calibration) combined. Variant vs baseline (same seed and traffic): use
                    # total_s_se_probes of both runs (see the module docstring)
                    "total_s_se": round(math.hypot(sd / math.sqrt(len(trips)), cal["run_to_run_sd_s"]), 1) if sd is not None else None,
                    "total_s_se_probes": round(sd / math.sqrt(len(trips)), 1) if sd is not None else None,
                    "run_to_run_sd_s": cal["run_to_run_sd_s"],
                    "probe_trips": len(trips)},
        "junctions": junction_stats(outdir, secs, info),
        "warnings": warnings,
        "inputs": {"counts_source": "estimated" if measured else "assumed", "label": "estimated" if measured else "assumed",
                   "volume_scale": asked_scale, "cross_traffic": cross,
                   **({"hour": hour, "day": "july" if is_july(day) else day, "hour_volume_scale": hour_cfg.get("volume_scale", 1.0),
                       "hour_cap_scale": hour_cfg.get("cap_scale", 1.0), "volume_scale_effective": round(volume_scale, 4)} if hour_cfg else {}),
                   "through_vph": round(through["fwd"] * volume_scale),
                   "through_vph_by_direction": {"A->B": round(through["fwd"] * volume_scale), "B->A": round(through["rev"] * volume_scale)},
                   "cross_vph_per_approach": round(CROSS_VPH * volume_scale),
                   "corridor_volumes": corridor_volumes(outdir, secs, info["corridor"], approaches),
                   **({"weather": rain} if rain else {}),
                   **({"live_trip": {k: live.get(k) for k in ("as_of", "bucket", "total_s", "confidence", "confidence_label",
                                                               "july_same_hour_total_s", "july_same_hour_label", "hour", "now_hour",
                                                               "hour_clamped", "stale", "data_label")},
                       "live_fit": {k: hour_cfg.get(k) for k in ("volume_scale", "cap_scale", "tomtom_total_s", "sim_total_s", "ratio",
                                                                 "within_tolerance", "target_basis")}}
                      if hour_cfg and day == "live" and live else {}),
                   "sources": sources_note(cal, info) + ([{"input": f"weather what-if: {weather}", "label": "estimated",
                                                           "source": f"{WEATHER_LABEL}: speed caps x per-leg factor relative to "
                                                                     f"{rain['relative_to']}; demand and signals unchanged"}] if rain else [])
                              + ([{"input": "water-logging hotspots: " + ", ".join(rain["affected_junctions"]), "label": WATERLOG_LABEL,
                                   "source": f"data/weather/waterlogging_points.json (reported in public sources, not measured by us): extra speed cap "
                                             f"within {rain['waterlogging_radius_m']:.0f} m of each reported junction, on top of the leg factor"}]
                                 if rain and rain.get("waterlogging") else [])
                   + ([{"input": f"time of day {hour_cfg.get('window') or hour_label(hour)}", "label": "calibrated",
                                                           "source": f"traffic x{hour_cfg.get('volume_scale', 1.0)}, speed caps x{hour_cfg.get('cap_scale', 1.0)} on the all-day "
                                                                     f"calibration, fitted to TomTom {hour_cfg.get('period', 'hourly leg times')} "
                                                                     + ("(calibration_hourly.json)" if is_july(day) else
                                                                        "(the July hour adjusted to the TomTom live trip estimate, calibration_live.json)"
                                                                        if day == "live" else
                                                                        "(the July hour adjusted on demand, calibration_days.json)")}] if hour_cfg else []),
                   "calibrated_to": f"TomTom Traffic Stats job {TOMTOM_JOB}, July 2026 06:00-23:00, leg speeds",
                   "speeds_source": "counted (TomTom probe data)", "probes_arrived": min(n_probes), "teleports": teleports,
                   "vehicles_loaded": loaded, "vehicles_not_inserted": waiting,
                   "sections": [{"from": s["points"][0], "to": s["points"][-1], "sim_seconds": s["end"], "probes": n}
                                for s, n in zip(secs, n_probes)],
                   "sim_seconds": max(s["end"] for s in secs), "wall_seconds": round(time.time() - t0, 1), "templates": sorted(kinds)},
        "frames_path": str(frames_path) if frames_path else None,
        "frames_window": frames_info(window) if frames_path else None,
        "roads_path": str(write_roads(net, outdir)),
        "probe_tracks_path": str(tracks_path),
        "probe_tracks": tracks,
    }
    (outdir / "result.json").write_text(json.dumps(result, indent=1))
    return result


def section_lon(k):
    """Longitude range whose vehicles section k contributes to the frames (each stretch shown by one section only)."""
    pts = cn.CORRIDOR["points"]
    ids, lon = [p["id"] for p in pts], {p["id"]: p["lon"] for p in pts}
    p1, p2 = SECTIONS[k]
    i1, i2 = ids.index(p1), ids.index(p2)
    return (-999 if i1 == 0 else lon[p1] + 0.0015, 999 if i2 == len(pts) - 1 else lon[p2] + 0.0015)


def replay_frames(prev, window, run_id=None):
    """Another frames window for a finished run: `prev` is its C5 result (its folder still on disk). The run's own
    network, routes and detector files are simulated again, each section only up to the window's end, recording the
    frames. Driving is deterministic, so these are exactly the frames a full run would record (checked by
    check_playback.py); the numbers, roads and probe tracks are prev's (copied). About half the time of a full run.
    Returns the new run's C5 result (frames_replayed_from: prev's run_id). FileNotFoundError when prev's files are gone."""
    src = Path(prev["roads_path"]).parent
    n = len(SECTIONS)
    files = [src / "variant.net.xml", src / "roads.geojson", Path(prev.get("probe_tracks_path") or src / "probes.json")]
    files += [src / f"{x}_{k}.xml" for k in range(n) for x in ("routes", "det")]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        raise FileNotFoundError(f"run {prev.get('run_id')}: {', '.join(missing)} no longer on disk")
    run_id = run_id or "rc_" + uuid.uuid4().hex[:8]
    outdir = OUT / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for f in files:
        shutil.copy(f, outdir / f.name)
    net_path = outdir / "variant.net.xml"
    net = sumolib.net.readNet(str(net_path))
    secs = [{"k": k, "lon": section_lon(k), "end": int(window[1] + FRAMES[2])} for k in range(n)]
    with ThreadPoolExecutor(min(n, PARALLEL)) as pool:
        frame_files = list(pool.map(lambda s: simulate(net, net_path, s, outdir, True, SEED, window), secs))
    frames_path = merge_frames(frame_files, outdir / "frames.jsonl")
    for k in range(n):        # outputs of the shortened sections are partial: only the frames count
        for name in (f"probes_{k}.xml", f"fcd_{k}.xml", f"stats_{k}.xml", f"e2_{k}.xml", f"counts_{k}.xml"):
            (outdir / name).unlink(missing_ok=True)
    res = json.loads(json.dumps({k: v for k, v in prev.items() if k not in ("fingerprint", "cached", "requested")}))
    res.update(run_id=run_id, frames_path=str(frames_path), frames_window=frames_info(window), roads_path=str(outdir / "roads.geojson"),
               probe_tracks_path=str(outdir / files[2].name), frames_replayed_from=prev["run_id"])
    res["inputs"] = {**res["inputs"], "frames_wall_seconds": round(time.time() - t0, 1)}
    (outdir / "result.json").write_text(json.dumps(res, indent=1))
    return res


def sources_note(cal, sources):
    """What the run's inputs are and how sure we are of each: measured (counted), estimated, assumed or calibrated."""
    span = sources.get("tomtom_span")
    return [
        {"input": "leg travel times (calibration target)", "label": "counted",
         "source": f"TomTom Traffic Stats job {TOMTOM_JOB}: probe vehicles, July 2026 every day 06:00-23:00"},
        {"input": "traffic on every arm of every junction at " + (", ".join(sorted(j for j, v in sources["cross"].items() if v["label"] == "estimated")) or "no junction"),
         "label": "estimated", "source": f"TomTom Junction Analytics (model estimates from probe data), mean over {span or 'no data yet'} "
                                         f"(minutes within 06-23 h) x cross_scale; corridor approaches topped up only by the shortfall "
                                         f"to TomTom's volume (traffic already arriving counted first)"},
        {"input": "where each arm's traffic goes (turn shares)", "label": "estimated",
         "source": f"TomTom Junction Analytics turn ratios (left/straight/right/U by angle, probe-weighted) where at least "
                   f"{MIN_TURN_PROBES} probes back them; elsewhere {', '.join(f'{k} {v:.0%}' for k, v in ASSUMED_TURNS.items())} (assumed)"},
        {"input": "arms without TomTom (j01, j05: TomTom's areas are elsewhere; j11: none; side streets)", "label": "assumed",
         "source": f"{ASSUMED_VPH_PER_LANE} veh/h per lane, at most {ASSUMED_VPH_MAX} veh/h per arm"},
        {"input": "through traffic taking a flyover", "label": "measured", "source": f"{FLYOVER_SHARE:.0%} (docs/driver-behaviour.md s1)"},
        {"input": "end-to-end corridor volume", "label": "calibrated" if cal["calibrated"] else "assumed",
         "source": "set so the corridor approaches at the TomTom junctions carry TomTom's volume (inputs.corridor_volumes)"},
        {"input": "speed cap per leg (side friction: bus stops, parking, pedestrians, autos)", "label": "calibrated" if cal["calibrated"] else "assumed",
         "source": "set so the probe cars' leg times match TomTom's"},
        {"input": "signal plans", "label": "assumed",
         "source": f"docs/driver-behaviour.md s5: {cn.YELLOW_S} s amber, free left in every phase; main x minor junctions: corridor both "
                   f"ways, a {cn.RIGHT_TURN_S} s protected right-turn phase, then the side road, {cn.SIGNAL_CYCLE_S} s cycle, corridor "
                   f">= {MIN_SHARE_MAIN:.0%} of the green; big junctions ({', '.join(sorted(cn.BIG_JUNCTIONS))}): one approach at a "
                   f"time, {cn.BIG_CYCLE_S} s cycle (corridor_net.signal_plans)"},
        {"input": "corridor green share where calibrated", "label": "calibrated" if cal["green_share"] else "assumed",
         "source": ", ".join(f"{j} {v:.0%}" for j, v in sorted(cal["green_share"].items())) or "none"},
        {"input": "vehicle mix", "label": "assumed", "source": ", ".join(f"{k} {v:.0%}" for k, v in MIX.items())
                                                              + "; fast riders: 30% of two-wheelers, 50% of autos (docs/driver-behaviour.md s2 table)"},
        {"input": "driver behaviour (sizes, speeds, gaps, reaction times, amber/red running, box blocking, giving way)", "label": "assumed",
         "source": f"docs/driver-behaviour.md s2-s7 (VEHICLES); capacity x{CAPACITY} via following headways (tau, minGap / {HEADWAY_FACTOR}, estimated); "
                   f"imperfection {SIGMA_NOTE}; side-street traffic forces in below {SIDE_SPEED:g} m/s ({SIDE_PROB:.0%}, estimated); "
                   f"lateral behaviour (filtering, weaving) and creeping past the stop line not modelled (non-sublane model)"},
        {"input": "joining traffic", "label": "assumed", "source": f"drives {JOIN_M / 1000:.0f} km along the corridor, then turns off"},
        {"input": "junction delay on the corridor's approaches (calibration target)", "label": "estimated",
         "source": f"TomTom Junction Analytics, mean over {span or 'no data yet'} (evening); capped at each leg's all-day time "
                   f"above {FREE_KMH} km/h free flow (inputs.corridor_volumes: tomtom_delay_s vs sim_delay_s)"},
        {"input": "traffic at Lakdikapul (B)", "label": "assumed",
         "source": "disperses before the last ~130 m (a 5-into-2-lane give-way merge); only probe cars drive on"},
    ]


# ---------- calibration ----------
def junction_delays(res, tt):
    """{junction id: (simulated, target delay s)} at the junctions where TomTom measures the corridor's approaches:
    means over both directions. Target: TomTom's delay (evening mean, estimated), but at most the time TomTom's leg
    into the junction takes above free flow (FREE_KMH), so the all-day leg times stay reachable."""
    pts = [p["id"] for p in cn.CORRIDOR["points"]]
    rows = {}
    for r in res["inputs"]["corridor_volumes"]:
        if r.get("sim_delay_s") is not None and r.get("tomtom_delay_s") is not None:
            rows.setdefault(r["junction_id"], []).append((r["sim_delay_s"], r["tomtom_delay_s"]))
    out = {}
    for jid, pairs in rows.items():
        k = pts.index(jid) - 1                                     # the leg ending at the junction
        excess = max(10.0, tt[k][3] - tt[k][2] / (FREE_KMH / 3.6))
        out[jid] = (statistics.mean(a for a, _ in pairs), min(statistics.mean(b for _, b in pairs), excess))
    return out


def calibrate(rounds=8, fresh=False, through=None, cross_scale=None):
    """Fit the calibrated knobs to TomTom and write calibration.json (see the module docstring). Each round runs the
    baseline, then per leg: too fast -> lower its speed cap; too slow -> raise the cap, and once the cap is at MAX_KMH
    (the time is lost at the junction, not on the road) give the corridor more green at the junction ending the leg.
    Traffic is lowered 10% when the network does not cope (vehicles stuck or unable to enter) or a leg is still too slow
    with the corridor's green at its limit, but never below MIN_DEMAND of the starting volumes. `through` and
    `cross_scale` set the starting volumes (default: calibration.json, else the assumed defaults). Keeps the round
    closest to TomTom."""
    tt = tomtom_legs()
    pts = [p["id"] for p in cn.CORRIDOR["points"]]
    cal = calibration()
    caps = list(cal["cap_kmh"]) if cal["calibrated"] and not fresh else [min(MAX_KMH, 2.0 * kmh) for *_, kmh in tt]
    shares = {} if fresh else {j: max(min_share(j), v) for j, v in cal["green_share"].items()}
    through, cross_scale = dict(through or cal["through_vph"]), cross_scale or cal["cross_scale"]
    floor = {"through": {d: v * MIN_DEMAND for d, v in through.items()}, "cross": cross_scale * MIN_DEMAND}
    base = sumolib.net.readNet(str(NET))
    groups = cn.junction_groups(base)
    signals = {j for j, g in groups.items() if g}
    cross, corridor, span = junction_counts(base, groups, cn.route(base), cn.route(base, reverse=True))   # live TomTom data
    arms = junction_arms(base, {j: [n.getID() for n in g] for j, g in groups.items() if g})
    tomtom = {"span": span, "cross": cross, "corridor": corridor, "arms": arms,
              "note": "TomTom Junction Analytics means (minutes within 06-23 h) used by every run: corridor approaches "
                      "(volume check, delay targets) and every arm of every junction (junction_arms: volumes and turn "
                      "shares); frozen at calibration, refreshed by calibrate()"}
    best = None
    for r in range(rounds):
        res = run(caps=caps, shares=shares, through=through, cross_scale=cross_scale, frames=False, run_id=f"calib_{r}", tomtom=tomtom)
        shutil.rmtree(OUT / f"calib_{r}", ignore_errors=True)
        legs, j = res["journey"]["legs"], res["journey"]
        ratios = [l["time_s"] / l["tomtom_time_s"] for l in legs]
        score = max(abs(x - 1) for x in ratios) + 2 * abs(j["total_s"] / j["tomtom_total_s"] - 1)
        print(f"round {r}: sim {j['total_s'] / 60:.1f} min vs TomTom {j['tomtom_total_s'] / 60:.1f} min | leg ratios "
              f"{[round(x, 2) for x in ratios]} | shares {shares} | through {through} cross {cross_scale} | delays { {jid: (round(a), round(b)) for jid, (a, b) in junction_delays(res, tt).items()} } | {res['inputs']['wall_seconds']} s", flush=True)
        score += 0.25 * sum(abs(d - t) / max(t, 10) for d, t in junction_delays(res, tt).values()) / max(1, len(junction_delays(res, tt)))
        if best is None or score < best[0]:
            best = (score, list(caps), dict(shares), res, dict(through), cross_scale)
        if all(abs(x - 1) < 0.07 for x in ratios) and abs(j["total_s"] / j["tomtom_total_s"] - 1) < 0.03:
            break
        overloaded, touched = False, set()
        for k, x in enumerate(ratios):
            new = max(8.0, min(MAX_KMH, caps[k] * x ** 0.8))
            end = pts[k + 1]
            if x > 1.07 and caps[k] >= MAX_KMH - 0.1 and end in signals:
                if shares.get(end, cn.CORRIDOR_GREEN_SHARE) >= MAX_SHARE - 1e-6:
                    overloaded = True       # still too slow with the corridor's green at its limit: too much traffic
                shares[end] = round(min(MAX_SHARE, shares.get(end, cn.CORRIDOR_GREEN_SHARE) + 0.1), 2)
                touched.add(end)
            caps[k] = round(new, 1)
        # junction delay: where TomTom measures the corridor's approaches, the corridor's green moves the simulated
        # delay towards target_delay() (TomTom's, at most the leg's time over free flow); the caps then refit the legs
        for jid, (simd, target) in junction_delays(res, tt).items():
            if jid in touched or jid not in signals:
                continue
            share = shares.get(jid, cn.CORRIDOR_GREEN_SHARE)
            if simd < 0.75 * target and ratios[pts.index(jid) - 1] < 1.07:
                shares[jid] = round(max(min_share(jid), share - 0.05), 2)
            elif simd > 1.33 * target + 5:
                shares[jid] = round(min(MAX_SHARE, share + 0.05), 2)
        inp = res["inputs"]
        if inp["teleports"] > 0.01 * inp["vehicles_loaded"] or inp["vehicles_not_inserted"] > NOT_INSERTED_OK * inp["vehicles_loaded"]:
            overloaded = True
        if overloaded and cross_scale * 0.9 >= floor["cross"] - 1e-6:
            through = {d: round(v * 0.9) for d, v in through.items()}
            cross_scale = round(cross_scale * 0.9, 3)
    _, caps, shares, res, through, cross_scale = best
    # run-to-run noise: the calibrated baseline with other seeds (everything else equal)
    others = [run(caps=caps, shares=shares, through=through, cross_scale=cross_scale, frames=False, run_id=f"calib_seed{sd_}",
                  tomtom=tomtom, seed=sd_) for sd_ in (SEED + 1, SEED + 2, SEED + 3)]
    for sd_ in (SEED + 1, SEED + 2, SEED + 3):
        shutil.rmtree(OUT / f"calib_seed{sd_}", ignore_errors=True)
    totals = [res["journey"]["total_s"]] + [o["journey"]["total_s"] for o in others]
    print(f"seeds {SEED}..{SEED + 3}: trip {[round(t / 60, 1) for t in totals]} min", flush=True)
    j = res["journey"]
    CALIBRATION.write_text(json.dumps({
        "target": f"TomTom Traffic Stats job {TOMTOM_JOB}: Lingampally -> Lakdikapul, July 2026 every day 06:00-23:00",
        "cap_kmh": caps, "green_share": shares, "through_vph": through, "cross_scale": cross_scale, "tomtom": tomtom,
        "knobs": {
            "cap_kmh": "calibrated: speed cap per leg (A->j01 ... j11->B) standing in for side friction (bus stops, parking, "
                       "pedestrians, autos), both directions",
            "green_share": f"calibrated: corridor share of the green time at junctions where the leg was still too slow at "
                           f"{MAX_KMH} km/h; elsewhere {cn.CORRIDOR_GREEN_SHARE} (assumed)",
            "through_vph": "calibrated: end-to-end corridor traffic per direction; starts at THROUGH_VPH (assumed) and is "
                           "lowered 10% at a time while a leg stays too slow with the corridor's green at its limit",
            "cross_scale": "calibrated as through_vph: share of TomTom Junction Analytics' evening cross-road volumes used for the all-day "
                           "average"},
        "result": {"sim_total_s": j["total_s"], "tomtom_total_s": j["tomtom_total_s"],
                   "legs": [{"leg": f"{l['from_id']}->{l['to_id']}", "sim_s": l["time_s"], "tomtom_s": l["tomtom_time_s"],
                             "ratio": round(l["time_s"] / l["tomtom_time_s"], 3)} for l in j["legs"]],
                   "junction_delays": {jid: {"sim_s": round(a, 1), "target_s": round(b, 1)} for jid, (a, b) in junction_delays(res, tt).items()},
                   "total_s_se": j.get("total_s_se"),
                   "corridor_volumes": res["inputs"]["corridor_volumes"], "teleports": res["inputs"]["teleports"],
                   "vehicles_loaded": res["inputs"]["vehicles_loaded"], "vehicles_not_inserted": res["inputs"]["vehicles_not_inserted"],
                   "probes_arrived": res["inputs"]["probes_arrived"], "wall_seconds": res["inputs"]["wall_seconds"],
                   "inputs": res["inputs"]["sources"]},
        "run_to_run_sd_s": round(statistics.stdev(totals), 1), "seed_totals_s": totals,
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))
    return caps, shares


def calibrate_hourly(hours=None, rounds=8, tol=0.03, refit=False):
    """Fit each hour of the day to TomTom's hourly trip time and write calibration_hourly.json. Needs TomTom rows in
    data/raw/corridor_legs_tomtom.csv whose period is one hour (row_hour(): e.g. "2026-07-01..2026-07-31 08:00-09:00").
    Starting from the all-day calibration, per hour: the simulated trip is too slow -> less traffic, too fast -> more
    traffic (volume scale within HOUR_VOLUME; secant steps once two runs are in). Only when the volume is at its limit
    (or the network jams: vehicles stuck or unable to enter) are the legs' speed caps scaled (HOUR_CAP; side friction
    differs by hour too), never above HOUR_MAX_KMH. Stops within `tol` (3%) of TomTom's trip; keeps the closest round.
    The file is written after every hour, so a long run can be stopped and resumed (hours already in it are redone
    only when asked for by number)."""
    data = tomtom_hours()
    asked = list(hours) if hours else None
    todo = [h for h in (asked or sorted(data)) if h in data and h in HOURS]
    if not todo:
        print("no hourly TomTom rows in", LEGS_CSV.name, "(periods like '2026-07-01..2026-07-31 08:00-09:00'); nothing to do", flush=True)
        return None
    cal = calibration()
    if not cal["calibrated"]:
        raise RuntimeError("run calibrate() first: the hourly scales sit on top of the all-day calibration")
    out = hourly_calibration() or {}
    out.setdefault("hours", {})
    prev_fits = dict(out["hours"]) if refit else {}
    if refit:          # the model changed: refit every hour, each starting from its own previous scales
        out["hours"] = {}
    if not asked and not refit:
        todo = [h for h in todo if str(h) not in out["hours"]]
    # start with the hour most like the all-day average (the all-day calibration fits it best), then outwards, so
    # each hour starts from a fitted neighbour
    ref = allday_trip_s()
    first = min(todo, key=lambda h: abs((data[h].get("trip_total_s") or ref) - ref))
    todo.sort(key=lambda h: (abs(h - first), h))
    for h in todo:
        d = data[h]
        # warm start from the nearest hour already fitted (neighbouring hours are alike): its volume, and its speed-cap
        # scale only when its volume was at the floor (the caps were needed there)
        done = [int(k) for k in out["hours"] if int(k) != h]
        near = out["hours"][str(min(done, key=lambda k: (abs(k - h), k)))] if done else None
        v, cs = 1.0, 1.0
        if near and near.get("tomtom_trip_total_s") and d.get("trip_total_s"):
            t_near = float(near["tomtom_total_s"])
            t_est = t_near * d["trip_total_s"] / near["tomtom_trip_total_s"]     # this hour's target, roughly
            if near["volume_scale"] <= HOUR_VOLUME[0] + 1e-6 and near["cap_scale"] > 1:    # caps regime (light traffic)
                v, cs = HOUR_VOLUME[0], max(1.0, round(near["cap_scale"] * (t_near / t_est) ** 1.3, 3))
            else:
                slope = near.get("slope_s_per_volume") or 600.0
                v = round(min(HOUR_VOLUME[1], max(HOUR_VOLUME[0], near["volume_scale"] + (t_est - t_near) / slope)), 3)
        own = (prev_fits or {}).get(str(h))
        if own:        # refitting an hour (the model changed): start from its own previous scales
            v, cs = float(own["volume_scale"]), float(own.get("cap_scale", 1.0))
        hist, best, seen = [], None, []
        for r in range(rounds):
            caps = [min(HOUR_MAX_KMH, round(c * cs, 1)) for c in cal["cap_kmh"]]
            rid = f"calib_h{h:02d}_{r}"
            res = run(volume_scale=v, caps=caps, frames=False, run_id=rid)
            shutil.rmtree(OUT / rid, ignore_errors=True)
            j, inp = res["journey"], res["inputs"]
            target, how = trip_target(d, j["legs"], j["tomtom_total_s"], allday_trip_s())
            if target is None:
                raise RuntimeError(f"hour {h:02d}: the hourly rows have neither leg times nor a trip total")
            t = j["total_s"]
            stuck = inp["teleports"] > 0.01 * inp["vehicles_loaded"] or inp["vehicles_not_inserted"] > NOT_INSERTED_OK * inp["vehicles_loaded"]
            err = t / target - 1
            seen.append((v, cs, t, stuck))
            print(f"{hour_label(h)} round {r}: sim {t / 60:.1f} min vs TomTom {target / 60:.1f} min ({how}) | volume x{v:.3f} "
                  f"caps x{cs:.3f} | {'JAMMED ' if stuck else ''}{inp['wall_seconds']} s", flush=True)
            if best is None or (stuck, abs(err)) < (best["stuck"], abs(best["err"])):
                best = {"v": v, "cs": cs, "t": t, "target": target, "how": how, "err": err, "stuck": stuck, "rounds": r + 1,
                        "legs": j["legs"], "warnings": res["warnings"]}
            if abs(err) < tol and not stuck:
                break
            hist.append((v, cs, t, stuck))
            at_floor, at_ceiling = v <= HOUR_VOLUME[0] + 1e-6, v >= HOUR_VOLUME[1] - 1e-6
            if stuck:                                   # too much traffic for the network
                if not at_floor and (cs <= 1.0 or err < 0):     # (faster caps never clear a jam caused by volume)
                    v = max(HOUR_VOLUME[0], round(v * 0.85, 3))
                else:
                    cs = round(min(HOUR_CAP[1], cs * 1.1), 3)
            elif cs == 1.0 and not (err > 0 and at_floor) and not (err < 0 and (at_ceiling or any(s for _, _, _, s in hist))):
                same = [(hv, ht) for hv, hcs, ht, hs in hist if hcs == cs and not hs]
                if len(same) >= 2 and abs(same[-1][1] - same[-2][1]) > 1:
                    (v0, t0_), (v1, t1_) = same[-2], same[-1]
                    nv = v1 + (target - t1_) * (v1 - v0) / (t1_ - t0_)
                else:
                    nv = v * (target / t) ** 3      # the trip responds weakly to traffic away from capacity: a bold first step
                v = round(min(HOUR_VOLUME[1], max(HOUR_VOLUME[0], v / 1.5, min(v * 1.5, nv))), 3)
            else:                                       # volume at its limit: the time is in the road speeds
                ncs = cs * (t / target) ** 1.3
                if (cs > 1 > ncs) or (cs < 1 < ncs):
                    ncs = 1.0                           # back to the plain caps: the volume takes over again
                cs = round(min(HOUR_CAP[1], max(HOUR_CAP[0], ncs)), 3)
            if hist and (v, cs) == hist[-1][:2]:
                break                                   # nothing left to change
        b = best
        # how the trip time responds to traffic near the fit (s per unit of volume scale): fit_day_hour's first step
        near = sorted((p for p in seen if p[1] == b["cs"] and not p[3] and abs(p[0] - b["v"]) > 1e-6), key=lambda p: abs(p[0] - b["v"]))
        slope = round((b["t"] - near[0][2]) / (b["v"] - near[0][0]), 1) if near and abs(b["t"] - near[0][2]) > 1 else None
        out["hours"][str(h)] = {
            "volume_scale": b["v"], "cap_scale": b["cs"], "tomtom_total_s": round(b["target"]), "sim_total_s": b["t"],
            "ratio": round(b["t"] / b["target"], 3), "within_tolerance": abs(b["err"]) < tol and not b["stuck"],
            "target_basis": b["how"], "tomtom_trip_total_s": d.get("trip_total_s"), "period": d["period"], "job": d["job"],
            "label": hour_label(h), "rounds": b["rounds"], "jammed": b["stuck"], "warnings": b["warnings"],
            "slope_s_per_volume": slope if slope and slope > 0 else None,
            "legs": [{"leg": f"{l['from_id']}->{l['to_id']}", "distance_m": l["distance_m"], "sim_s": l["time_s"],
                      "tomtom_s": round(l["distance_m"] / (d["legs"][(l["from_id"], l["to_id"])][2] / 3.6)) if b["how"] == "leg speeds" else None}
                     for l in b["legs"]]}
        out.update({
            "target": "TomTom Traffic Stats hourly leg times (rows of data/raw/corridor_legs_tomtom.csv covering one hour), July 2026",
            "base_calibration": json.loads(CALIBRATION.read_text()).get("calibrated_at") if CALIBRATION.exists() else None,
            "method": "per hour: volume scale on the all-day traffic (through and cross), then, only if the volume is at its "
                      f"limits {HOUR_VOLUME} or the network jams, a scale on the legs' speed caps {HOUR_CAP}; target within "
                      f"{tol:.0%} of TomTom's trip (calibrate_hourly)",
            "knobs": {"volume_scale": "calibrated: multiplies all traffic of the all-day calibration for this hour",
                      "cap_scale": "calibrated: multiplies every leg's speed cap (side friction) for this hour; 1 = unchanged"},
            "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        HOURLY.write_text(json.dumps(out, indent=1))
        print(f"{hour_label(h)}: volume x{b['v']}, caps x{b['cs']}, sim {b['t'] / 60:.1f} vs TomTom {b['target'] / 60:.1f} min", flush=True)
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["calibrate"]:
        calibrate()
    elif sys.argv[1:2] == ["calibrate_hourly"]:       # calibrate_hourly [refit] [8 9 ...]
        args = [a for a in sys.argv[2:] if a != "refit"]
        calibrate_hourly([int(a) for a in args] or None, refit="refit" in sys.argv[2:])
    elif sys.argv[1:2] == ["fit_day"]:        # fit_day 2026-07-08 18: fit (or reuse) one day and hour, print the result
        res = run(hour=int(sys.argv[3]), day=sys.argv[2], frames=False)
        print(res["time"], round(res["journey"]["total_s"] / 60, 1), "min vs TomTom", round(res["journey"]["tomtom_total_s"] / 60, 1))
    elif sys.argv[1:2] == ["fit_live"]:      # fit_live live.json [hour]: live.json = a frozen live trip (live_trip.frozen)
        lv = json.loads(Path(sys.argv[2]).read_text())
        res = run(hour=int(sys.argv[3]) if len(sys.argv) > 3 else lv["hour"], day="live", live=lv, frames=False)
        print(res["time"], round(res["journey"]["total_s"] / 60, 1), "min vs live", round(res["journey"]["tomtom_total_s"] / 60, 1))
    elif sys.argv[1:2] == ["run"]:
        ivs = [{"junction_id": a.split(":")[0], "kind": a.split(":")[1], "params": {}} for a in sys.argv[2:]]
        res = run(ivs, frames=False)
        j = res["journey"]
        print(f"{res['variant_id']}: {j['total_s'] / 60:.1f} min (TomTom {j['tomtom_total_s'] / 60:.1f}), {j['distance_m'] / 1000:.1f} km, "
              f"{res['inputs']['wall_seconds']} s wall, teleports {res['inputs']['teleports']}")
        for l in j["legs"]:
            print(f"  {l['from_id']:>14} -> {l['to_id']:<13} {l['distance_m']:>5} m  {l['time_s'] / 60:5.1f} min  (TomTom {l['tomtom_time_s'] / 60:5.1f})")
        for x in res["junctions"]:
            print(f"  {x['id']} {x['name'][:24]:24} delay {x['avg_delay_s']:6.1f} s  queue {x['max_queue_m']:4} m  veh {x['vehicles']}")
