.PHONY: setup dev smoke
setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt
dev:
	. .venv/bin/activate && cd backend && MOCK_SIM=$${MOCK_SIM:-1} uvicorn app.main:app --reload --port 8000
smoke:
	. .venv/bin/activate && python scripts/smoke_test.py
