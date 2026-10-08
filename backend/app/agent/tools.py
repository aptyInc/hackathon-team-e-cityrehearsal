"""Agent tool definitions for the Claude API (tool use). Owner: AI agent workstream.

Each tool maps to a backend endpoint, so every agent action is logged as a run.
Wire these into a Claude tool-use loop in agent.py (TODO).
"""
TOOLS = [
    {"name": "diagnose", "description": "Run the baseline for the case and report where queues start.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"]}},
    {"name": "create_variant", "description": "Create an option from a template (C3 variant spec). Templates: signal_retime, junction_redesign, bus_lane, widening, flyover.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}, "variant_id": {"type": "string"},
                      "template": {"type": "string"}, "params": {"type": "object"}}, "required": ["case_id", "variant_id", "template", "params"]}},
    {"name": "run_scenario", "description": "Run a variant at a traffic volume scale (1.0 = base) and return the C2 result.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}, "variant_id": {"type": "string"},
                      "volume_scale": {"type": "number"}}, "required": ["case_id", "variant_id"]}},
    {"name": "compare", "description": "Rank all runs in the case by delay at the target junction and ripple at nearby junctions.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"]}},
    {"name": "write_brief", "description": "Write the one-page decision brief from the case's evidence.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"]}},
]
