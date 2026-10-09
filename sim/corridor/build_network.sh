#!/usr/bin/env bash
# Lingampally -> Lakdikapul corridor network: main roads within 350 m of the route TomTom measured
# (sim/corridor/corridor.osm.xml, Overpass query in overpass_query.txt). Same settings as the YMCA network:
# left-hand traffic, Hyderabad speed/lane defaults, flyovers keep their height, signals guessed at big junctions.
set -euo pipefail
: "${SUMO_HOME:=$(python3 -c "import sumo; print(sumo.SUMO_HOME)")}"
cd "$(dirname "$0")"
netconvert --osm-files corridor.osm.xml -o corridor.net.xml \
  --type-files "$SUMO_HOME/data/typemap/osmNetconvert.typ.xml,../networks/india_urban.typ.xml" \
  --lefthand --output.street-names --output.original-names \
  --remove-edges.isolated --osm.layer-elevation 6 \
  --geometry.remove --ramps.guess --junctions.join --junctions.join-dist 15 \
  --tls.guess-signals --tls.discard-simple --tls.join \
  --no-turnarounds.except-deadend
echo "Built sim/corridor/corridor.net.xml"
python3 corridor_net.py signals
echo "Signals at the corridor junctions (assumed two-stage plans, 120 s cycle), corridor lanes linked through"
