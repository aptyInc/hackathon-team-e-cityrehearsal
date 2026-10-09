"""Gariahat flyover backtest: does our simulator reproduce what Maitra et al. (2004) found?

The study (data/gariahat/, IIT Kharagpur, European Transport 27) modelled Gariahat crossing and Ballygunge Phari,
the next junction north on Gariahat Road, before and after the Gariahat flyover. Its finding: the flyover cuts the
average delay at Gariahat by ~75%, but the delay on Phari's approach from Gariahat more than doubles, so the problem
moves north instead of going away. This script runs the same two layouts with the study's counted volumes and turns
in SUMO and puts our before/after changes next to the study's.

    python sim/gariahat/backtest.py                       # 3 seeds -> sim/gariahat/results.json + chart.png
    python sim/gariahat/backtest.py --seeds 1 --frames    # also C1 frames in $CR_SIM_OUT/gariahat (default sim/out)

Network: built here from plain XML, not from the OSM conversion in sim/networks (that one has no signals and ~2,000
side-street edges). Two signalised junctions at their real positions, the five + four roads the study counted,
~930 m of Gariahat Road between them with one side street, and in the "after" layout a 2+2-lane flyover over
Gariahat crossing with its landings where OpenStreetMap has them. Approach widths are the study's (Table 3).
"""
import argparse, csv, gzip, json, math, os, statistics as st, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path

import sumolib

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA = ROOT / "data/gariahat"
OUT = Path(os.environ.get("CR_SIM_OUT", ROOT / "sim/out")) / "gariahat"
_BIN = Path(sys.executable).parent  # SUMO tools installed in the venv (make setup-sim); else from PATH
NETCONVERT = str(_BIN / "netconvert") if (_BIN / "netconvert").exists() else "netconvert"
SUMO = str(_BIN / "sumo") if (_BIN / "sumo").exists() else "sumo"

# ---------------------------------------------------------------- geometry (lon, lat from OpenStreetMap)
NODES = {
    "G": (88.36525, 22.51965),     # Gariahat crossing: Gariahat Road x Rash Behari Avenue
    "P": (88.36596, 22.52793),     # Ballygunge Phari
    "GS1": (88.36611, 22.51697),   # south flyover landing (Gol Park side)
    "GS0": (88.36680, 22.51400),   # Gariahat Road, south
    "GW0": (88.35963, 22.51857),   # Rash Behari Avenue, west (towards Deshpriya Park)
    "GE0": (88.37000, 22.52160),   # Rash Behari Avenue, east
    "GN1": (88.36529, 22.52292),   # north flyover landing
    "M": (88.36595, 22.52542),     # Mandeville Gardens: side street between the two junctions
    "ME0": (88.36780, 22.52480),
    "PN0": (88.36570, 22.53350),   # Gariahat Road north of Phari
    "PNE0": (88.36884, 22.53100),  # Broad Street
    "PW0": (88.36023, 22.52800),   # Ballygunge Circular Road
    "PSW0": (88.36145, 22.52544),  # Hazra Road
}
# Study approach letter -> road (arm). Gariahat: A and C are the flyover axis (paper section 3.2). C = from the
# south: its straight traffic plus the turns towards Phari (C 1,091 + B left 185 + D right 153 = 1,429/h) is close to
# Phari's counted approach C (1,527/h); with A from the south it would be 1,278/h. B = west (Deshpriya Park side,
# Fig. 1), D = east. (estimated)
GARIAHAT = {"A": "GN", "B": "GW", "C": "GS", "D": "GE"}
# Phari: C = from Gariahat (paper). Of the 24 ways to put A, B, D, E on the other four roads, three send ~1,050
# veh/h towards Gariahat (Gariahat's counted approach A: 1,068/h); only this one also fits the widths: the narrow
# 6.7 / 6.9 m approaches on the two-lane Hazra Road and Ballygunge Circular Road, the widest (10.6 m) on the
# four-lane Gariahat Road north. (estimated)
PHARI = {"A": "PSW", "B": "PW", "C": "PS", "D": "PNE", "E": "PN"}
ARM_END = {"GN": "GN1", "GS": "GS1", "GW": "GW0", "GE": "GE0", "PS": "M", "PN": "PN0", "PNE": "PNE0", "PW": "PW0", "PSW": "PSW0"}
STUDY_NAME = {"G": "Gariahat", "P": "Phari"}
CLASSES = {"car": "car", "two_wheeler": "two_wheeler", "bus": "bus", "minibus": "minibus", "auto": "auto"}
SPEED, FLYOVER_SPEED, FLYOVER_LANES = 11.11, 13.89, 2   # 40 km/h at grade, 50 km/h flyover (assumed); 2 lanes each way (OSM)

# ---------------------------------------------------------------- signals
# Gariahat: two phases, Gariahat Road (A + C) then Rash Behari Avenue (B + D) (paper: "two-phase"). Phari: three
# phases (paper). The paper does not say which roads share a phase; we use Gariahat Road (C + E), Hazra Road with
# Ballygunge Circular Road (A + B), Broad Street (D) alone, the grouping that fits the paper's before-flyover delays
# (Table 6: A below B and C above E in a shared phase, the small Broad Street flow with the longest delay, 77.8 s, as
# on a short green). Our first try, (C + E), (A + D), (B), left Phari over capacity before the flyover. (estimated)
# Cycle 150 s everywhere: the one cycle the paper reports (Gariahat after the flyover); Phari's timing does not change
# with the flyover, as in the paper. (assumed) Green split in proportion to each phase's busiest approach, in
# passenger-car units per lane (Webster's rule, equal saturation flow per lane). (assumed)
PHASES = {"G": [["A", "C"], ["B", "D"]], "P": [["C", "E"], ["A", "B"], ["D"]]}
CYCLE = {("G", False): 150, ("G", True): 150, ("P", False): 150, ("P", True): 150}
YELLOW, ALL_RED, MIN_GREEN = 3, 2, 10
PCU = {"car": 1.0, "two_wheeler": 0.5, "bus": 3.0, "minibus": 1.5, "auto": 0.8}   # IRC-style factors (assumed)
# Inside the junction box, vehicles obey the lights but do not give way to each other: movements that are green
# together weave through, as Kolkata traffic does and as the study's model assumed (it simulated each approach on its
# own). With SUMO's strict give-way rules ("traffic_light"), right-turners waiting for gaps in a saturated oncoming
# stream blocked their lanes and Phari locked up even before the flyover (assumed; CR_JTYPE=traffic_light to compare).
JUNCTION_TYPE = os.environ.get("CR_JTYPE", "traffic_light_unregulated")

SENSITIVITY = [1.1, 1.2, 1.3]   # extra traffic into Phari from Gariahat after the flyover (what-if, not from the study)
WARMUP, PEAK = 600, 3600        # 10 min to fill the roads, then the study's peak hour
CLEAR = 1800                    # after the hour, let queued vehicles finish (they are counted)
STEP = 0.5


# ---------------------------------------------------------------- inputs
def read_study():
    vols = {(r["intersection"], r["approach"]): r for r in csv.DictReader(open(DATA / "volumes.csv"))}
    turns = {(r["intersection"], r["approach"]): {k: float(r[f"{k}_pct"] or 0) / 100 for k in ("left", "straight", "right")}
             for r in csv.DictReader(open(DATA / "turns.csv"))}
    return vols, turns, list(csv.DictReader(open(DATA / "study_results.csv")))


VOLS, TURNS, STUDY = read_study()


def class_vols(j, letter, scale=1.0):
    r = VOLS[(STUDY_NAME[j], letter)]
    return {c: float(r[c]) * scale for c in CLASSES}


def xy(lon, lat, ref=NODES["G"]):
    return ((lon - ref[0]) * 111320 * math.cos(math.radians(ref[1])), (lat - ref[1]) * 110750)


def bearing(a, b):
    (ax, ay), (bx, by) = xy(*NODES[a]), xy(*NODES[b])
    return math.degrees(math.atan2(bx - ax, by - ay)) % 360


def exit_shares(j, letter):
    """Study turn shares (left / straight / right) -> exit road. Straight = the exit closest to straight ahead;
    every exit to its left counts as left, to its right as right; a share is split evenly between exits of one kind
    (Phari has five roads). Left-hand traffic: left turns are the easy ones. (assumed)"""
    arms = JUNCTION[j]
    arm = arms[letter]
    heading = bearing(ARM_END[arm], j)
    ang = {x: (bearing(j, ARM_END[x]) - heading + 180) % 360 - 180 for x in arms.values() if x != arm}
    s = min(ang, key=lambda x: abs(ang[x]))
    kinds = {"straight": [s], "left": [x for x in ang if ang[x] < ang[s]], "right": [x for x in ang if ang[x] > ang[s]]}
    out = {}
    for kind, xs in kinds.items():
        for x in xs:
            out[x] = out.get(x, 0.0) + TURNS[(STUDY_NAME[j], letter)][kind] / len(xs)
    return {x: v for x, v in out.items() if v > 0}


JUNCTION = {"G": GARIAHAT, "P": PHARI}


# ---------------------------------------------------------------- network
def lanes_for(width):
    """Lanes = width / 3 m, rounded down (min 2); lane width = width / lanes, so the full measured width is used."""
    n = max(2, int(width // 3.0))
    return n, round(width / n, 2)


def width(j, arm):
    letter = {v: k for k, v in JUNCTION[j].items()}[arm]
    return float(VOLS[(STUDY_NAME[j], letter)]["width_m"])


def edge_list(after: bool):
    """(id, from, to, width in m | 'side' | 'flyover', name). Outbound width = the same road's inbound width (assumed)."""
    E = [("GW0_G", "GW0", "G", width("G", "GW"), "Rash Behari Avenue"), ("G_GW0", "G", "GW0", width("G", "GW"), "Rash Behari Avenue"),
         ("GE0_G", "GE0", "G", width("G", "GE"), "Rash Behari Avenue"), ("G_GE0", "G", "GE0", width("G", "GE"), "Rash Behari Avenue"),
         ("GS0_GS1", "GS0", "GS1", width("G", "GS"), "Gariahat Road"), ("GS1_GS0", "GS1", "GS0", width("G", "GS"), "Gariahat Road"),
         ("GS1_G", "GS1", "G", width("G", "GS"), "Gariahat Road"), ("G_GS1", "G", "GS1", width("G", "GS"), "Gariahat Road"),
         # between the junctions: northbound = Phari approach C, southbound = Gariahat approach A
         ("G_GN1", "G", "GN1", width("P", "PS"), "Gariahat Road"), ("GN1_M", "GN1", "M", width("P", "PS"), "Gariahat Road"),
         ("M_P", "M", "P", width("P", "PS"), "Gariahat Road"),
         ("P_M", "P", "M", width("G", "GN"), "Gariahat Road"), ("M_GN1", "M", "GN1", width("G", "GN"), "Gariahat Road"),
         ("GN1_G", "GN1", "G", width("G", "GN"), "Gariahat Road"),
         ("ME0_M", "ME0", "M", "side", "Mandeville Gardens"), ("M_ME0", "M", "ME0", "side", "Mandeville Gardens")]
    names = {"PN": "Gariahat Road", "PNE": "Broad Street", "PW": "Ballygunge Circular Road", "PSW": "Hazra Road"}
    for arm in ("PN", "PNE", "PW", "PSW"):
        E += [(f"{ARM_END[arm]}_P", ARM_END[arm], "P", width("P", arm), names[arm]),
              (f"P_{ARM_END[arm]}", "P", ARM_END[arm], width("P", arm), names[arm])]
    if after:
        E += [("flyover_n", "GS1", "GN1", "flyover", "Gariahat Flyover"), ("flyover_s", "GN1", "GS1", "flyover", "Gariahat Flyover")]
    return E


def build_network(after: bool, out: Path, tll: Path | None = None) -> Path:
    tag = "after" if after else "before"
    tmp = OUT / "build"; tmp.mkdir(parents=True, exist_ok=True)
    nod = ["<nodes>"] + [f'  <node id="{n}" x="{lon}" y="{lat}" type="{JUNCTION_TYPE if n in ("G", "P") else "priority"}"/>'
                         for n, (lon, lat) in NODES.items()] + ["</nodes>"]
    edg = ["<edges>"]
    for eid, a, b, w, name in edge_list(after):
        if w == "flyover":
            attrs = f'numLanes="{FLYOVER_LANES}" speed="{FLYOVER_SPEED}" priority="14" width="3.5"'
        elif w == "side":
            attrs = 'numLanes="1" speed="8.33" priority="5" width="3.5"'
        else:
            n, lw = lanes_for(w)
            attrs = f'numLanes="{n}" speed="{SPEED}" priority="12" width="{lw}"'
        edg.append(f'  <edge id="{eid}" from="{a}" to="{b}" name="{name}" {attrs}/>')
    edg.append("</edges>")
    (tmp / f"{tag}.nod.xml").write_text("\n".join(nod)); (tmp / f"{tag}.edg.xml").write_text("\n".join(edg))
    cmd = [NETCONVERT, "-n", str(tmp / f"{tag}.nod.xml"), "-e", str(tmp / f"{tag}.edg.xml"), "--proj.utm",
           "--lefthand", "--no-turnarounds", "--tls.yellow.time", str(YELLOW), "--output.street-names", "-o", str(out)]
    if tll:
        cmd += ["--tllogic-files", str(tll)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-1500:])
    return out


def approach_edge(j, arm):
    return {"GN": "GN1_G", "GS": "GS1_G", "PS": "M_P"}.get(arm, f"{ARM_END[arm]}_{j}")


def at_grade_vols(j, letter, after):
    """Vehicles per class that use the signal. After the flyover, straight traffic from Gariahat A and C is on the
    flyover (paper Table 7)."""
    v = class_vols(j, letter)
    if after and j == "G" and letter in ("A", "C"):
        k = 1 - TURNS[("Gariahat", letter)]["straight"]
        v = {c: x * k for c, x in v.items()}
    return v


def signal_plans(net_path: Path, after: bool, out: Path) -> Path:
    """Fixed-time plans in netconvert's tlLogic format, built on the link order of `net_path`."""
    root = ET.parse(net_path).getroot()
    net = sumolib.net.readNet(str(net_path))
    xml = ["<additional>"]
    for j in ("G", "P"):
        links = {}   # linkIndex -> (approach edge, direction)
        for inl, outl, idx in net.getTLS(j).getConnections():
            c = next(c for c in inl.getEdge().getConnections(outl.getEdge()) if c.getFromLane() == inl and c.getToLane() == outl)
            links[idx] = (inl.getEdge().getID(), c.getDirection())
        n = len(links)
        req = {int(r.get("index")): r.get("foes")[::-1] for r in root.find(f"junction[@id='{j}']").iter("request")}
        letter_of = {approach_edge(j, arm): L for L, arm in JUNCTION[j].items()}
        y = {}   # passenger-car units per lane per hour
        for L, arm in JUNCTION[j].items():
            pcu = sum(PCU[c] * v for c, v in at_grade_vols(j, L, after).items())
            lanes = lanes_for(float(VOLS[(STUDY_NAME[j], L)]["width_m"]))[0]
            if after and j == "G" and L in ("A", "C"):
                lanes = 1   # under the flyover only left-turners are left at grade, all in the kerb lane
            y[L] = pcu / lanes
        groups = PHASES[j]
        crit = [max(y[L] for L in g) for g in groups]
        cycle = CYCLE[(j, after)]
        usable = cycle - len(groups) * (YELLOW + ALL_RED)
        greens = [max(MIN_GREEN, usable * c / sum(crit)) for c in crit]
        greens = [round(g * usable / sum(greens)) for g in greens]
        xml.append(f'  <tlLogic id="{j}" type="static" programID="0" offset="0">')
        xml.append(f'    <!-- {STUDY_NAME[j]} {"after" if after else "before"}: cycle {cycle} s; pcu per lane per hour '
                   + ", ".join(f"{L} {y[L]:.0f}" for L in sorted(y)) + "; phases " + " | ".join("+".join(g) for g in groups) + " -->")
        for g, green in zip(groups, greens):
            active = [i for i in range(n) if letter_of.get(links[i][0]) in g]
            state = ["r"] * n
            for i in active:
                state[i] = "G"
            if JUNCTION_TYPE == "traffic_light":
                # strict give-way: of two crossing links green together, the turning one (right turn) yields
                for i in active:
                    for k in active:
                        if i != k and req[i][k] == "1" and state[i] == "G" and state[k] == "G":
                            weak = i if links[i][1] in ("r", "R") or (links[k][1] not in ("r", "R") and i > k) else k
                            state[weak] = "g"
            s = "".join(state)
            xml.append(f'    <phase duration="{green}" state="{s}"/>')
            xml.append(f'    <phase duration="{YELLOW}" state="{s.replace("G", "y").replace("g", "y")}"/>')
            xml.append(f'    <phase duration="{ALL_RED}" state="{"r" * n}"/>')
        xml.append("  </tlLogic>")
    xml.append("</additional>")
    out.write_text("\n".join(xml) + "\n")
    return out


def networks():
    """Before and after networks with our signal plans compiled in. Small; kept in sim/gariahat/net."""
    nd = HERE / "net"; nd.mkdir(exist_ok=True)
    paths = {}
    for after in (False, True):
        tag = "after" if after else "before"
        net = build_network(after, nd / f"gariahat_{tag}.net.xml")
        tll = signal_plans(net, after, nd / f"gariahat_{tag}.tll.xml")
        paths[tag] = build_network(after, nd / f"gariahat_{tag}.net.xml", tll)
    return paths


# ---------------------------------------------------------------- demand
ROUTE_IN = {"GW": ["GW0_G"], "GE": ["GE0_G"], "GS": ["GS0_GS1", "GS1_G"], "GN": ["M_GN1", "GN1_G"],
            "PS": ["M_P"], "PN": ["PN0_P"], "PNE": ["PNE0_P"], "PW": ["PW0_P"], "PSW": ["PSW0_P"]}
ROUTE_OUT = {"GW": ["G_GW0"], "GE": ["G_GE0"], "GS": ["G_GS1", "GS1_GS0"], "GN": ["G_GN1", "GN1_M"],
             "PS": ["P_M"], "PN": ["P_PN0"], "PNE": ["P_PNE0"], "PW": ["P_PW0"], "PSW": ["P_PSW0"]}

VTYPES = """  <!-- Indian mixed traffic, as in sim/scripts/build_demand.py (close following, sublane filtering; assumed).
       Minibus added for the Kolkata counts. -->
  <vType id="two_wheeler" vClass="motorcycle" length="1.9" width="0.75" minGap="0.5" tau="0.6" maxSpeed="16.7" accel="3.0" decel="5.0"
         speedFactor="normc(0.85,0.1,0.5,1.2)" latAlignment="arbitrary" minGapLat="0.3" lcSublane="2.0" lcPushy="0.6"/>
  <vType id="auto" vClass="passenger" length="2.7" width="1.4" minGap="0.7" tau="0.7" maxSpeed="12.5" accel="1.8" decel="4.0"
         speedFactor="normc(0.85,0.1,0.5,1.1)" latAlignment="arbitrary" minGapLat="0.4" lcSublane="1.5" lcPushy="0.4"/>
  <vType id="car" vClass="passenger" length="4.3" width="1.75" minGap="1.0" tau="0.8" maxSpeed="16.7" accel="2.6" decel="4.5"
         speedFactor="normc(0.85,0.1,0.5,1.2)" latAlignment="center" minGapLat="0.5"/>
  <vType id="minibus" vClass="bus" length="7.5" width="2.2" minGap="1.2" tau="0.9" maxSpeed="13.9" accel="1.4" decel="4.0"
         speedFactor="normc(0.8,0.1,0.5,1.0)" latAlignment="center" minGapLat="0.5"/>
  <vType id="bus" vClass="bus" length="11" width="2.5" minGap="1.5" tau="1.0" maxSpeed="13.9" accel="1.2" decel="4.0"
         speedFactor="normc(0.8,0.1,0.5,1.0)" latAlignment="center" minGapLat="0.6"/>
"""


def od_flows(after: bool, scale: float = 1.0):
    """[(flow id, origin approach label, edges, {class: veh/h})]. Every vehicle starts on a counted approach and
    follows the study's turn shares; vehicles leaving one junction towards the other continue with the other
    junction's shares, so the traffic between them is the junctions' own output, not a separate input."""
    flows = []

    def add(fid, origin, edges, per_class):
        per_class = {c: v for c, v in per_class.items() if v >= 0.5}
        if per_class:
            flows.append((fid, origin, edges, per_class))

    def onward(j, arm_from_other, path, per_class, fid, origin):
        """Continue through junction j, entered from the road towards the other junction."""
        L = {v: k for k, v in JUNCTION[j].items()}[arm_from_other]
        for x, s in exit_shares(j, L).items():
            out = ROUTE_OUT[x]
            if after and j == "G" and x == "GS":          # southbound straight: over the flyover
                edges = path[:-1] + ["flyover_s", "GS1_GS0"]   # path ends ... M_GN1, GN1_G
            else:
                edges = path + out
            add(f"{fid}_{x}", origin, edges, {c: v * s for c, v in per_class.items()})

    for j, other_arm, link in (("G", "GN", ["G_GN1", "GN1_M", "M_P"]), ("P", "PS", ["P_M", "M_GN1", "GN1_G"])):
        other = "P" if j == "G" else "G"
        for L, arm in JUNCTION[j].items():
            if arm == other_arm:
                continue      # fed by the other junction
            per_class = class_vols(j, L, scale)
            for x, s in exit_shares(j, L).items():
                pc = {c: v * s for c, v in per_class.items()}
                fid = f"{STUDY_NAME[j][0]}{L}_{x}"
                if x == other_arm:
                    path = ROUTE_IN[arm] + link
                    if after and j == "G" and arm == "GS":    # northbound straight: over the flyover
                        path = ["GS0_GS1", "flyover_n", "GN1_M", "M_P"]
                    onward(other, "PS" if other == "P" else "GN", path, pc, fid, f"{STUDY_NAME[j]} {L}")
                else:
                    add(fid, f"{STUDY_NAME[j]} {L}", ROUTE_IN[arm] + ROUTE_OUT[x], pc)
    # Side street between the junctions: tops up each junction's approach from the other to its counted volume
    # (Phari C 1,527/h, Gariahat A 1,068/h) with that approach's vehicle mix. (estimated)
    for j, arm, letter, path in (("P", "PS", "C", ["ME0_M", "M_P"]), ("G", "GN", "A", ["ME0_M", "M_GN1", "GN1_G"])):
        target = float(VOLS[(STUDY_NAME[j], letter)]["total"]) * scale
        arriving = sum(sum(pc.values()) for _, o, e, pc in flows if path[1] in e and not o.startswith(STUDY_NAME[j]))  # via M_P / M_GN1
        gap = target - arriving
        if gap > 1:
            mix = class_vols(j, letter); tot = sum(mix.values())
            onward(j, arm, path, {c: gap * v / tot for c, v in mix.items()}, f"side{letter}{j}", "side street")
    return flows


def write_routes(after: bool, out: Path, scale: float = 1.0, phari_inflow: float = 1.0) -> Path:
    """`phari_inflow` multiplies all traffic arriving at Phari from the Gariahat side (sensitivity test only)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f"<!-- Gariahat backtest traffic ({'after' if after else 'before'} the flyover), built by sim/gariahat/backtest.py.",
             "     Volumes per approach and class: Maitra et al. 2004 Table 3 (counted). Turn shares: Table 4 (counted).",
             "     Same traffic before and after (the study re-routes the same counted volumes; Table 7 = straight A/C traffic on the flyover).",
             "     Random (exponential) arrivals; side-street top-up between the junctions (estimated)."
             + (f" Sensitivity: traffic into Phari from Gariahat x {phari_inflow}." if phari_inflow != 1 else "") + " -->",
             "<routes>", VTYPES]
    end = WARMUP + PEAK
    for fid, origin, edges, per_class in od_flows(after, scale):
        k = phari_inflow if "M_P" in edges else 1.0
        for c, vph in per_class.items():
            vph *= k
            lines.append(f'  <flow id="{fid}_{c}" type="{c}" begin="0" end="{end}" period="exp({vph / 3600:.6f})" '
                         f'departLane="best" departSpeed="max" departPosLat="random"><route edges="{" ".join(edges)}"/></flow>')
    lines.append("</routes>")
    out.write_text("\n".join(lines) + "\n")
    return out


# ---------------------------------------------------------------- measurement
def detectors(net_path: Path, after: bool, out: Path) -> Path:
    """One entry-exit (E3) detector per counted approach: time lost from the start of the approach road to just
    past the stop line (flyover users: to the start of the flyover, so they count with ~0 delay, as in the study)."""
    net = sumolib.net.readNet(str(net_path))
    lanes = lambda e: [l.getID() for l in net.getEdge(e).getLanes()]  # noqa: E731
    xml = ["<additional>"]
    for j, arms in JUNCTION.items():
        exits = [ROUTE_OUT[x][0] for x in arms.values()]
        for L, arm in arms.items():
            ex = list(exits)
            if after and j == "G" and arm in ("GS", "GN"):
                ex.append("flyover_n" if arm == "GS" else "flyover_s")
            if j == "P" and arm == "PS":
                entries = ["G_GN1", "ME0_M"] + (["flyover_n"] if after else [])
            elif j == "G" and arm == "GN":
                entries = ["P_M", "ME0_M"]
            else:
                entries = [ROUTE_IN[arm][0]]
            xml.append(f'  <entryExitDetector id="{STUDY_NAME[j]}_{L}" period="{WARMUP}" file="e3.xml" timeThreshold="2" speedThreshold="1.4">')
            for e in entries:
                pos = 15 if e == ROUTE_IN[arm][0] and not (j == "G" and arm == "GN") else 1
                xml += [f'    <detEntry lane="{l}" pos="{pos}"/>' for l in lanes(e)]
            xml += [f'    <detExit lane="{l}" pos="1"/>' for e in ex for l in lanes(e)]
            xml.append("  </entryExitDetector>")
    xml.append("</additional>")
    out.write_text("\n".join(xml) + "\n")
    return out


def approach_chain(j, arm, after):
    """Edges of an approach from the stop line upstream (for queue lengths)."""
    return {("G", "GS"): ["GS1_G", "GS0_GS1"], ("G", "GN"): ["GN1_G", "M_GN1", "P_M"],
            ("P", "PS"): ["M_P", "GN1_M", "G_GN1"]}.get((j, arm), ROUTE_IN[arm])


def run_one(after: bool, seed: int, net_path: Path, frames: bool = False, scale: float = 1.0, phari_inflow: float = 1.0) -> dict:
    tag = "after" if after else "before"
    rd = OUT / (f"{tag}_s{seed}" + (f"_in{phari_inflow:g}" if phari_inflow != 1 else "")); rd.mkdir(parents=True, exist_ok=True)
    rou = write_routes(after, rd / "routes.rou.xml", scale, phari_inflow)
    add = detectors(net_path, after, rd / "det.add.xml")
    cmd = [SUMO, "-n", str(net_path), "-r", str(rou), "-a", str(add), "--seed", str(seed), "--step-length", str(STEP),
           "--lateral-resolution", "0.8", "--end", str(WARMUP + PEAK + CLEAR), "--time-to-teleport", "600",
           "--tripinfo-output", str(rd / "tripinfo.xml"), "--queue-output", str(rd / "queue.xml"),
           "--statistic-output", str(rd / "stats.xml"), "--no-step-log", "--no-warnings", "--collision.action", "warn"]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=rd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"sumo exit {p.returncode}: {(p.stderr + p.stdout)[-1500:]}")
    wall = time.time() - t0
    res = measure(rd, after)
    res["wall_seconds"] = round(wall, 1)
    if frames:  # same seed, same traffic, stopped after the frame window: identical vehicles, small temporary file
        begin = WARMUP + 600
        fcd = [SUMO, "-n", str(net_path), "-r", str(rou), "--seed", str(seed), "--step-length", str(STEP), "--lateral-resolution", "0.8",
               "--end", str(begin + FRAME_SECONDS), "--time-to-teleport", "600", "--no-step-log", "--no-warnings",
               "--collision.action", "warn", "--fcd-output", str(rd / "fcd.xml.gz"), "--fcd-output.geo", "true",
               "--device.fcd.begin", str(begin), "--device.fcd.period", "1", "--fcd-output.attributes", "id,type,x,y,angle,speed,lane,pos"]
        p = subprocess.run(fcd, cwd=rd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"sumo (frames) exit {p.returncode}: {(p.stderr + p.stdout)[-1500:]}")
        res["frames_path"] = str(write_frames(rd / "fcd.xml.gz", OUT / f"frames_{tag}.jsonl", net_path))
    for f in ("queue.xml", "tripinfo.xml"):
        (rd / f).unlink(missing_ok=True)
    return res


def measure(rd: Path, after: bool) -> dict:
    # E3: per approach, vehicles leaving after the warm-up
    e3 = {}
    for iv in ET.parse(rd / "e3.xml").getroot().iter("interval"):
        if float(iv.get("begin")) < WARMUP:
            continue
        d = e3.setdefault(iv.get("id"), [0, 0.0])
        n = int(iv.get("vehicleSum")); d[0] += n; d[1] += n * float(iv.get("meanTimeLoss") if n else 0)
    # insertion backlog: vehicles that could not enter because the queue reached the edge of the model
    backlog = {}
    trips = []
    for t in ET.parse(rd / "tripinfo.xml").getroot().iter("tripinfo"):
        dd = float(t.get("departDelay")); wanted = float(t.get("depart")) - dd
        if WARMUP <= wanted < WARMUP + PEAK:
            fid = t.get("id")
            key = ("Gariahat_" if fid[0] == "G" else "Phari_" if fid[0] == "P" else "side_") + fid[1]
            backlog.setdefault(key, []).append(dd)
            trips.append((fid, float(t.get("duration")) + dd))
    # queues: per step, from the stop line upstream while edges are (nearly) full
    q = {}
    for ts in ET.parse(rd / "queue.xml").getroot().iter("data"):
        per_edge = {}
        for lane in ts.iter("lane"):
            e = lane.get("id").rsplit("_", 1)[0]
            per_edge[e] = max(per_edge.get(e, 0.0), float(lane.get("queueing_length") or 0))
        for j, arms in JUNCTION.items():
            for L, arm in arms.items():
                total = 0.0
                for e in approach_chain(j, arm, after):
                    ql = per_edge.get(e, 0.0); total += ql
                    if ql < 0.8 * EDGE_LEN.get(e, 1e9):
                        break
                k = f"{STUDY_NAME[j]}_{L}"
                q[k] = max(q.get(k, 0.0), total)
    approaches = {}
    for k, (n, loss) in e3.items():
        bl = backlog.get(k, [])
        approaches[k] = {"vehicles": n, "avg_delay_s": round((loss + sum(bl)) / n, 1) if n else None,
                         "entry_wait_s": round(st.mean(bl), 1) if bl else 0.0, "max_queue_m": round(q.get(k, 0.0))}
    stats = ET.parse(rd / "stats.xml").getroot()
    tele = stats.find("teleports"); coll = stats.find("safety")
    # corridor: Gariahat Road end to end through both junctions (south of Gariahat <-> north of Phari)
    nb = [d for f, d in trips if f.startswith("GC_GN_PN")]
    sb = [d for f, d in trips if f.startswith("PE_PS_GS")]
    return {"approaches": approaches, "teleports": int(tele.get("total")) if tele is not None else 0,
            "collisions": int(coll.get("collisions")) if coll is not None else 0,
            "corridor_travel_time_s": {"northbound": round(st.mean(nb)) if nb else None, "southbound": round(st.mean(sb)) if sb else None}}


EDGE_LEN = {}


FRAME_SECONDS = 240   # C1 frames per layout: 4 minutes at one frame per second keeps each file under ~15 MB


def write_frames(fcd: Path, out: Path, net_path: Path, seconds: int = FRAME_SECONDS) -> Path:
    """C1 frames (contracts/vehicle_frame.schema.json), one per second, for `seconds` from the start of the fcd.
    Vehicles on the flyover get a height: 6 m, ramping over the first and last 80 m (assumed)."""
    n, t_first = 0, None
    with open(out, "w") as f, gzip.open(fcd, "rb") as src:
        for _, el in ET.iterparse(src, events=("end",)):
            if el.tag != "timestep":
                continue
            t = float(el.get("time"))
            t_first = t if t_first is None else t_first
            if t - t_first >= seconds:
                break
            vs = []
            for v in el.iter("vehicle"):
                lane, pos = v.get("lane", ""), float(v.get("pos") or 0)
                z = 0.0
                if lane.startswith("flyover"):
                    ln = EDGE_LEN.get(lane.rsplit("_", 1)[0], 600)
                    z = round(6.0 * min(1.0, pos / 80, (ln - pos) / 80), 1)
                vs.append({"id": v.get("id"), "type": "bus" if v.get("type") == "minibus" else v.get("type"),
                           "lon": round(float(v.get("x")), 6), "lat": round(float(v.get("y")), 6), "z": z,
                           "angle": round(float(v.get("angle")), 1), "speed": round(float(v.get("speed")), 2)})
            f.write(json.dumps({"t": t, "vehicles": vs}) + "\n"); n += 1
            el.clear()
    fcd.unlink(missing_ok=True)
    return out


# ---------------------------------------------------------------- the study's own numbers (study model, Tables 5, 6, 8)
STUDY_APPROACH_DELAY = {
    "before": {"Gariahat_A": 37.1, "Gariahat_B": 35.7, "Gariahat_C": 41.2, "Gariahat_D": 23.8,
               "Phari_A": 37.1, "Phari_B": 52.1, "Phari_C": 42.4, "Phari_D": 77.8, "Phari_E": 29.3},
    # after: Gariahat at-grade traffic only (Table 8); Phari C from section 3.2; other Phari approaches unchanged
    "after": {"Gariahat_A": 11.2, "Gariahat_B": 23.1, "Gariahat_C": 13.7, "Gariahat_D": 17.6,
              "Phari_A": 37.1, "Phari_B": 52.1, "Phari_C": 110.3, "Phari_D": 77.8, "Phari_E": 29.3},
}


def study_value(measure, where, when):
    for r in STUDY:
        if r["measure"] == measure and r["intersection"] == where:
            return float(r[f"{when}_flyover"])


def summarise(runs: list[dict], after: bool) -> dict:
    """Mean over seeds. Junction delay = vehicle-weighted mean of its approaches; vehicle-hours = delay x the
    study's counted peak-hour volume (the study's own method: 35.3 s x 3,886 veh = 38.1 veh-h)."""
    appr = {}
    for k in runs[0]["approaches"]:
        vals = [r["approaches"][k] for r in runs if r["approaches"].get(k, {}).get("avg_delay_s") is not None]
        appr[k] = {"avg_delay_s": round(st.mean(v["avg_delay_s"] for v in vals), 1),
                   "seed_range_s": [min(v["avg_delay_s"] for v in vals), max(v["avg_delay_s"] for v in vals)],
                   "vehicles": round(st.mean(v["vehicles"] for v in vals)),
                   "max_queue_m": round(st.mean(v["max_queue_m"] for v in vals)),
                   "entry_wait_s": round(st.mean(v["entry_wait_s"] for v in vals), 1)}
    junctions = []
    for j in ("Gariahat", "Phari"):
        ks = [k for k in appr if k.startswith(j)]
        per_seed = []
        for r in runs:
            a = r["approaches"]; n = sum(a[k]["vehicles"] for k in ks)
            per_seed.append(sum(a[k]["avg_delay_s"] * a[k]["vehicles"] for k in ks) / n)
        d = st.mean(per_seed)
        vol = study_value("peak-hour volume", j, "before")
        junctions.append({"id": j.lower(), "avg_delay_s": round(d, 1), "seed_range_s": [round(min(per_seed), 1), round(max(per_seed), 1)],
                          "max_queue_m": max(appr[k]["max_queue_m"] for k in ks), "vehicle_hours_delay": round(d * vol / 3600, 1),
                          "vehicles": sum(appr[k]["vehicles"] for k in ks)})
    pc = appr["Phari_C"]
    junctions.append({"id": "phari_approach_c", "avg_delay_s": pc["avg_delay_s"], "seed_range_s": pc["seed_range_s"],
                      "max_queue_m": pc["max_queue_m"], "vehicles": pc["vehicles"]})
    cor = {d: round(st.mean(r["corridor_travel_time_s"][d] for r in runs if r["corridor_travel_time_s"][d])) for d in ("northbound", "southbound")}
    warnings = []
    tele = sum(r["teleports"] for r in runs) / len(runs); coll = sum(r["collisions"] for r in runs) / len(runs)
    if tele:
        warnings.append(f"{tele:.0f} vehicles per run were moved past a gridlock (SUMO teleport after 600 s stuck)")
    if coll:
        warnings.append(f"{coll:.0f} touches per run where movements that are green together merge (junction box not "
                        "give-way regulated, see README); vehicles keep going")
    tag = "after" if after else "before"
    return {"run_id": f"gariahat_{tag}", "variant_id": f"gariahat_{tag}_flyover", "junctions": junctions,
            "corridor_travel_time_s": round((cor["northbound"] + cor["southbound"]) / 2),
            "corridor_travel_time_by_direction_s": cor, "approaches": appr, "warnings": warnings,
            "inputs": {"counts_source": "published_study (Maitra et al. 2004, Tables 3-4)", "label": "counted", "volume_scale": 1.0,
                       "seeds": [r["seed"] for r in runs], "step_length_s": STEP, "sublane_model": True,
                       "signal_cycle_s": {"gariahat": CYCLE[("G", after)], "phari": CYCLE[("P", after)]}},
            "wall_seconds_per_run": round(st.mean(r["wall_seconds"] for r in runs), 1)}


def row(label, sb, sa, mb, ma):
    s_pct, m_pct = (sa - sb) / sb * 100, (ma - mb) / mb * 100
    same = (s_pct > 0) == (m_pct > 0)
    ratio = m_pct / s_pct if s_pct else None
    verdict = "match" if same and 0.5 <= ratio <= 2.0 else "partial" if same else "mismatch"
    return {"measure": label, "study_before": sb, "study_after": sa, "study_change_pct": round(s_pct),
            "sim_before": mb, "sim_after": ma, "sim_change_pct": round(m_pct), "same_direction": same, "verdict": verdict}


def compare(before: dict, after: dict) -> list[dict]:
    """Sim change next to the study's change for each thing the study reported. Verdict per row: match = same
    direction and a change between half and double the study's; partial = same direction only."""
    jb = {j["id"]: j for j in before["junctions"]}; ja = {j["id"]: j for j in after["junctions"]}
    rows = [("Gariahat: average delay per vehicle (s)", "average delay per vehicle", "Gariahat", "gariahat", "avg_delay_s"),
            ("Phari: delay on the approach from Gariahat (s)", "average delay per vehicle", "Phari approach C (from Gariahat)", "phari_approach_c", "avg_delay_s"),
            ("Phari: average delay per vehicle (s)", "average delay per vehicle", "Phari", "phari", "avg_delay_s"),
            ("Gariahat: peak-hour delay (veh-h)", "total delay at peak hour", "Gariahat", "gariahat", "vehicle_hours_delay"),
            ("Phari: peak-hour delay (veh-h)", "total delay at peak hour", "Phari", "phari", "vehicle_hours_delay")]
    out = [row(label, study_value(m, w, "before"), study_value(m, w, "after"), jb[jid][f], ja[jid][f]) for label, m, w, jid, f in rows]
    mb = jb["gariahat"]["vehicle_hours_delay"] + jb["phari"]["vehicle_hours_delay"]
    ma = ja["gariahat"]["vehicle_hours_delay"] + ja["phari"]["vehicle_hours_delay"]
    out.append(row("Both junctions: peak-hour delay (veh-h)", study_value("total delay at peak hour", "both together", "before"),
                   study_value("total delay at peak hour", "both together", "after"), round(mb, 1), round(ma, 1)))
    return out


def chart(cmp: list[dict], out: Path, sens: list[dict] | None = None, after_c: float | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 4 if sens else 3, figsize=(12 if sens else 9, 3.4), dpi=100)
    if sens:
        ax = axes[3]
        xs = [0] + [s["extra_inflow_to_phari_pct"] for s in sens]
        ys = [after_c] + [s["phari_approach_c_delay_s"] for s in sens]
        ax.plot(xs, ys, "o-", color="#2f6fdb", label="CityRehearsal, after flyover")
        ax.axhline(cmp[1]["study_after"], color="#9aa5b1", ls="--", label=f"study after ({cmp[1]['study_after']:.0f} s)")
        ax.axhline(cmp[1]["sim_before"], color="#2f6fdb", ls=":", lw=1, label=f"ours before ({cmp[1]['sim_before']:.0f} s)")
        ax.set_xlabel("extra traffic into Phari from Gariahat, %", fontsize=8)
        ax.set_title("Phari approach from Gariahat:\nwhat if the flyover draws more traffic?", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False); ax.tick_params(labelsize=8)
        ax.legend(fontsize=7, frameon=False, loc="upper left")
    for ax, r in zip(axes, cmp[:3]):
        sv, mv = [r["study_before"], r["study_after"]], [r["sim_before"], r["sim_after"]]
        ax.bar([-0.18, 0.82], sv, 0.34, color="#9aa5b1", label="Study (2004 model)")
        ax.bar([0.18, 1.18], mv, 0.34, color="#2f6fdb", label="CityRehearsal (SUMO)")
        for i in (0, 1):
            ax.text(i - 0.18, sv[i], f"{sv[i]:.0f}", ha="center", va="bottom", fontsize=7)
            ax.text(i + 0.18, mv[i], f"{mv[i]:.0f}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks([0, 1], ["before flyover", "after flyover"], fontsize=8)
        ax.set_title(r["measure"].replace(" (s)", "").replace(": ", ":\n"), fontsize=9)
        ax.spines[["top", "right"]].set_visible(False); ax.tick_params(labelsize=8)
    axes[0].set_ylabel("delay, seconds per vehicle", fontsize=8)
    axes[0].legend(fontsize=7, frameon=False, loc="upper right")
    fig.suptitle("Gariahat flyover: delay before and after, 2004 study vs our simulator", fontsize=10)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--frames", action="store_true", help="also write 4 minutes of C1 frames per layout to $CR_SIM_OUT/gariahat")
    ap.add_argument("--no-sensitivity", action="store_true", help="skip the extra-inflow-to-Phari runs")
    ap.add_argument("--no-write", action="store_true", help="print only; keep results.json and chart.png as they are")
    args = ap.parse_args()
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    nets = networks()
    for p in nets.values():
        for e in sumolib.net.readNet(str(p)).getEdges():
            EDGE_LEN[e.getID()] = e.getLength()
    seeds = range(1, args.seeds + 1)
    jobs = [(after, seed, 1.0) for after in (False, True) for seed in seeds]
    if not args.no_sensitivity:
        jobs += [(True, seed, k) for k in SENSITIVITY for seed in seeds]
    with ThreadPoolExecutor(max_workers=min(7, len(jobs))) as pool:
        futs = {job: pool.submit(run_one, job[0], job[1], nets["after" if job[0] else "before"],
                                 args.frames and job[1] == 1 and job[2] == 1.0, 1.0, job[2]) for job in jobs}
        res = {job: dict(f.result(), seed=job[1]) for job, f in futs.items()}
    before = summarise([r for (a, _, k), r in res.items() if not a], False)
    after = summarise([r for (a, _, k), r in res.items() if a and k == 1.0], True)
    sens = []
    for k in ([] if args.no_sensitivity else SENSITIVITY):
        s = summarise([r for (a, _, kk), r in res.items() if a and kk == k], True)
        j = {x["id"]: x for x in s["junctions"]}
        sens.append({"extra_inflow_to_phari_pct": round((k - 1) * 100), "phari_approach_c_delay_s": j["phari_approach_c"]["avg_delay_s"],
                     "phari_avg_delay_s": j["phari"]["avg_delay_s"], "gariahat_avg_delay_s": j["gariahat"]["avg_delay_s"],
                     "phari_approach_c_max_queue_m": j["phari_approach_c"]["max_queue_m"]})
    for side, s in (("before", before), ("after", after)):
        for k, v in s["approaches"].items():
            v["study_avg_delay_s"] = STUDY_APPROACH_DELAY[side].get(k)
    cmp = compare(before, after)
    result = {"what": "Gariahat flyover backtest: Maitra et al. 2004 (study model) vs CityRehearsal SUMO, same layouts, same counted traffic",
              "comparison": cmp, "before": before, "after": after,
              "study_source": "data/gariahat/study_results.csv; per-approach delays from the paper's Tables 5, 6 and 8",
              "approach_letters": {"gariahat": GARIAHAT, "phari": PHARI, "label": "estimated (see README)"},
              "sensitivity_after_flyover": {
                  "what": "After the flyover, with X% more traffic arriving at Phari from the Gariahat side (the paper expects "
                          "the flyover to raise this inflow but does not say by how much)", "runs": sens},
              "wall_seconds_total": round(time.time() - t0)}
    print(f"{'measure':47} {'study before':>12} {'after':>6} {'change':>7} | {'sim before':>10} {'after':>6} {'change':>7}  verdict")
    for r in cmp:
        print(f"{r['measure']:47} {r['study_before']:12} {r['study_after']:6} {r['study_change_pct']:6}% | "
              f"{r['sim_before']:10} {r['sim_after']:6} {r['sim_change_pct']:6}%  {r['verdict']}")
    print("\napproach delay (s) sim before -> after  [study before -> after]")
    for k in before["approaches"]:
        b, a = before["approaches"][k], after["approaches"][k]
        print(f"  {k:11} {b['avg_delay_s']:6} -> {a['avg_delay_s']:6}   [{b['study_avg_delay_s']} -> {a['study_avg_delay_s']}]  "
              f"veh {b['vehicles']}/{a['vehicles']}  queue {b['max_queue_m']}/{a['max_queue_m']} m  entry wait {b['entry_wait_s']}/{a['entry_wait_s']} s")
    print("corridor travel time", before["corridor_travel_time_by_direction_s"], "->", after["corridor_travel_time_by_direction_s"])
    for s in sens:
        print(f"sensitivity: +{s['extra_inflow_to_phari_pct']}% into Phari from Gariahat -> Phari C {s['phari_approach_c_delay_s']} s, "
              f"Phari {s['phari_avg_delay_s']} s, queue {s['phari_approach_c_max_queue_m']} m")
    print("warnings", before["warnings"], after["warnings"], f"wall {result['wall_seconds_total']} s")
    if not args.no_write:
        (HERE / "results.json").write_text(json.dumps(result, indent=1) + "\n")
        chart(cmp, HERE / "chart.png", sens, cmp[1]["sim_after"])


if __name__ == "__main__":
    main()
