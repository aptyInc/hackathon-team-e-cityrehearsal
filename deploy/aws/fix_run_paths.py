"""Point the stored corridor runs at this machine's sim/out. The API stores each run's frames/roads/probe files as
absolute paths (`frames_path` etc. in runs.result) and `cache_lookup` only returns a cached result when those files
exist, so a decision log copied from a laptop misses the cache on the server until the prefix is rewritten.
Idempotent. Usage: python3 deploy/aws/fix_run_paths.py [db] [root]   (defaults: /opt/terascope)"""
import re, sqlite3, sys

root = (sys.argv[2] if len(sys.argv) > 2 else "/opt/terascope").rstrip("/")
db = sys.argv[1] if len(sys.argv) > 1 else f"{root}/backend/cityrehearsal.db"
pat = re.compile(r'"(frames_path|roads_path|probe_tracks_path)":\s*"(?!' + re.escape(root) + r'/)[^"]*?/sim/out/')
con = sqlite3.connect(db)
changed = 0
for rid, res in con.execute("SELECT id, result FROM runs").fetchall():
    new = pat.sub(lambda m: f'"{m.group(1)}": "{root}/sim/out/', res or "")
    if new != (res or ""):
        con.execute("UPDATE runs SET result=? WHERE id=?", (new, rid))
        changed += 1
con.commit()
print(f"run paths rewritten to {root}: {changed}")
