"""Aggregate a week's events (from build_week.py) with an optional prior week for trend.

Usage: python3 summarize.py week.json [prior.json] > summary.json
Hour totals count only events with verified start/end (flag is None).
"""
import json, sys
from collections import defaultdict


def agg(data):
    ev = data["events"]
    ok = [e for e in ev if e["minutes"] is not None]
    by = lambda key: _group(ok, ev, key)
    return {
        "events": len(ev), "verified": len(ok), "flagged": len(ev) - len(ok),
        "minutes": sum(e["minutes"] for e in ok),
        "sites": len({e["code"] for e in ev}),
        "by_category": by("category"), "by_district": by("district"), "by_site": by("site"),
    }


def _group(ok, ev, key):
    g = defaultdict(lambda: {"events": 0, "minutes": 0, "open": 0})
    for e in ev:
        g[e[key]]["events"] += 1
        if e["minutes"] is None:
            g[e[key]]["open"] += 1
    for e in ok:
        g[e[key]]["minutes"] += e["minutes"]
    return dict(sorted(g.items(), key=lambda kv: (-kv[1]["minutes"], -kv[1]["events"], kv[0])))


if __name__ == "__main__":
    cur = json.load(open(sys.argv[1]))
    out = {"week": agg(cur), "week_start": cur["week_start"], "week_end": cur["week_end"],
           "managers": cur["managers"], "districts_sites": cur["districts_sites"]}
    if len(sys.argv) > 2:
        prev = json.load(open(sys.argv[2]))
        out["prior"] = agg(prev)
        out["prior_start"], out["prior_end"] = prev["week_start"], prev["week_end"]
    json.dump(out, sys.stdout, indent=1)
