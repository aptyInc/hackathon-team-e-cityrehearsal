.PHONY: setup setup-sim network sim-test sim-run junction-data dev smoke
setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt
setup-sim:
	. .venv/bin/activate && pip install -r sim/requirements.txt && sumo --version | head -1
network:
	. .venv/bin/activate && bash sim/scripts/build_network.sh
sim-test:
	. .venv/bin/activate && export SUMO_HOME=$$(python -c "import sumo; print(sumo.SUMO_HOME)") && mkdir -p sim/out && \
	python $$SUMO_HOME/tools/randomTrips.py -n sim/networks/ymca.net.xml -e 600 -p 1.5 --fringe-factor 10 --validate \
	  -o sim/out/test.trips.xml -r sim/out/test.rou.xml --seed 42 > /dev/null && \
	sumo -n sim/networks/ymca.net.xml -r sim/out/test.rou.xml --end 900 --no-step-log --duration-log.statistics
sim-run:
	. .venv/bin/activate && python sim/runner.py '{"variant_id":"baseline","template":"baseline","params":{}}' --scale 1.0
junction-data:
	python3 data/tomtom/fetch_junction_archive.py 2026-10-08
dev:
	. .venv/bin/activate && cd backend && MOCK_SIM=$${MOCK_SIM:-1} uvicorn app.main:app --reload --reload-dir . --reload-dir ../sim --port 8000
smoke:
	. .venv/bin/activate && python scripts/smoke_test.py
