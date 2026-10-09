#!/usr/bin/env bash
# Gariahat backtest networks (Kolkata): "after" = today's roads with the Gariahat Flyover,
# "before" = the same roads with the flyover removed. Same settings as the YMCA network, except that
# residential roads are kept: OSM tags the ground-level Gariahat Road under the flyover as residential,
# and without it the Gariahat crossing (Gariahat Road x Rash Behari Avenue) disappears.
# Proof target (Maitra et al., IIT Kharagpur, 2004): adding the flyover cuts delay at Gariahat
# (Gariahat Road x Rash Behari Avenue) and raises it at Ballygunge Phari, the next junction north.
set -euo pipefail
: "${SUMO_HOME:=$(python3 -c "import sumo; print(sumo.SUMO_HOME)")}"
cd "$(dirname "$0")/../networks"
COMMON=(--type-files "$SUMO_HOME/data/typemap/osmNetconvert.typ.xml,india_urban.typ.xml"
  --lefthand --output.street-names
  --keep-edges.by-type highway.trunk,highway.trunk_link,highway.primary,highway.primary_link,highway.secondary,highway.secondary_link,highway.tertiary,highway.tertiary_link,highway.residential,highway.unclassified
  --remove-edges.isolated --osm.layer-elevation 6
  --geometry.remove --ramps.guess --junctions.join --tls.guess-signals --tls.discard-simple --output.original-names)
netconvert --osm-files gariahat.osm.xml -o gariahat_after.net.xml "${COMMON[@]}"
# Remove every edge named "Gariahat Flyover" (bridge and ramps). Edge ids shift when the flyover goes, so repeat
# until none are left.
list_flyover() { python3 -c "import sumolib,sys; n=sumolib.net.readNet(sys.argv[1]); print(','.join(e.getID() for e in n.getEdges() if 'flyover' in (e.getName() or '').lower()))" "$1"; }
REMOVE=$(list_flyover gariahat_after.net.xml)
for i in 1 2 3 4; do
  netconvert --osm-files gariahat.osm.xml -o gariahat_before.net.xml "${COMMON[@]}" --remove-edges.explicit "$REMOVE"
  LEFT=$(list_flyover gariahat_before.net.xml)
  [ -z "$LEFT" ] && break
  REMOVE="$REMOVE,$LEFT"
done
echo "Built gariahat_after.net.xml (with flyover) and gariahat_before.net.xml (flyover removed: $REMOVE)"
