#!/usr/bin/env bash
# Convert the OpenStreetMap extract into a SUMO network with lanes, signals and junctions.
set -euo pipefail
cd "$(dirname "$0")/../networks"
netconvert --osm-files ymca.osm.xml -o ymca.net.xml \
  --geometry.remove --ramps.guess --junctions.join --tls.guess-signals --tls.discard-simple \
  --output.original-names
echo "Built networks/ymca.net.xml — now check lane counts in netedit."
