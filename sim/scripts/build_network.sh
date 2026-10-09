#!/usr/bin/env bash
# Convert the OpenStreetMap extract into a SUMO network with lanes, signals and junctions.
# India drives on the left (--lefthand). Only main roads are kept: residential lanes and paths
# add simulation time without changing how YMCA Circle behaves.
# Hyderabad speed and lane defaults come from india_urban.typ.xml (used when OSM has no tag).
# Flyovers keep their height (--osm.layer-elevation) so the 3D view can lift them.
set -euo pipefail
: "${SUMO_HOME:=$(python3 -c "import sumo; print(sumo.SUMO_HOME)")}"
cd "$(dirname "$0")/../networks"
netconvert --osm-files ymca.osm.xml -o ymca.net.xml \
  --type-files "$SUMO_HOME/data/typemap/osmNetconvert.typ.xml,india_urban.typ.xml" \
  --lefthand --output.street-names \
  --keep-edges.by-type highway.trunk,highway.trunk_link,highway.primary,highway.primary_link,highway.secondary,highway.secondary_link,highway.tertiary,highway.tertiary_link,highway.unclassified \
  --keep-edges.components 1 \
  --osm.layer-elevation 6 \
  --geometry.remove --ramps.guess --junctions.join --tls.guess-signals --tls.discard-simple \
  --output.original-names
# Widen the roundabout ring and the 8 roads touching it to the widths measured in the 2020 study.
netconvert -s ymca.net.xml --edge-files ymca_widths.edg.xml --lefthand -o ymca.net.tmp.xml && mv ymca.net.tmp.xml ymca.net.xml
echo "Built networks/ymca.net.xml — now check lane counts in netedit."
