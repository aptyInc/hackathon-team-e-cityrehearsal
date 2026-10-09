"""Pre-compute the advisor's answer for every junction, with real simulations on a running API.

    cd backend && CR_DB=$PWD/cityrehearsal.db python -m app.agent.advise_all [--api http://localhost:8000] [j01 j02 ...]
                                                                            [--weather heavy_rain] [--fresh]

Runs go to the API's queue (POST /corridor/runs: one SUMO at a time, cache reused) and the advice rows land in CR_DB
(the API's own database, so GET /agent/advice serves them). Elevated junctions (j03 j04 j06 j07 j10 j11) are written
without simulations: "already crosses on a flyover" plus the alternative.
"""
import argparse, json, os, sys, time

from . import advisor, store


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("junctions", nargs="*", default=advisor.GROUND + list(advisor.ELEVATED))
    ap.add_argument("--api", default=os.getenv("CR_ADVISE_API", "http://localhost:8000"))
    ap.add_argument("--weather", default=None)
    ap.add_argument("--fresh", action="store_true", help="recompute even when fresh advice exists")
    a = ap.parse_args(argv)
    ver = advisor.model_version()
    print(f"model version {ver}; API {a.api}; DB {os.getenv('CR_DB', 'backend/cityrehearsal.db')}", flush=True)
    for jid in a.junctions:
        if not a.fresh:
            hit = store.latest_advice(jid, ver, a.weather)
            if hit and not hit["stale"]:
                print(f"{jid}: fresh advice exists ({hit['advice_id']}): {hit['advice']['verdict']}", flush=True)
                continue
        t0 = time.time()
        aid = store.create_advice(jid, a.weather, ver)
        runner = advisor.HttpRunner(a.api)
        try:
            adv = advisor.advise(jid, runner, a.weather, session_id="advisor")
        except Exception as e:
            store.finish_advice(aid, None, f"{type(e).__name__}: {e}")
            print(f"{jid}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        store.finish_advice(aid, adv)
        print(f"{jid} {adv['name']}: {adv['verdict']} ({len(adv['run_ids'])} runs, {time.time() - t0:.0f} s, brief {adv.get('brief_id')})", flush=True)
        for o in adv["options"]:
            print(f"   {o['rank']}. {o['kind']} {json.dumps(o['params'])}: {o['trip_change_min']:+.1f} min, rain {o['rain_change_min']}, "
                  f"1.1x {o['at_110_change_min']}, robust {o['robust']}, applicable {o['applicable']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
