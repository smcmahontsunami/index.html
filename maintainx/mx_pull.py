#!/usr/bin/env python3
"""Pull data from the MaintainX REST API (v1) to JSON + CSV.

Auth: set MAINTAINX_API_KEY in the environment. Never commit the key.

Usage:
  python3 mx_pull.py                       # pull all default resources
  python3 mx_pull.py workorders assets     # pull selected resources
  python3 mx_pull.py workorders --since 2026-01-01   # updatedAt filter (client-side)
Output: ./mx_data/<resource>.json and ./mx_data/<resource>.csv
"""
import argparse, csv, json, os, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("MAINTAINX_BASE_URL", "https://api.getmaintainx.com/v1")
DEFAULT_RESOURCES = ["workorders", "assets", "locations", "parts", "vendors",
                     "users", "teams", "meters", "purchaseorders", "categories"]
PAGE_SIZE = 100


def get(path, params, key, retries=5):
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}",
                                               "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(int(e.headers.get("Retry-After", 2 ** attempt)))
                continue
            raise SystemExit(f"{path}: HTTP {e.code} {e.read().decode()[:300]}")
    raise SystemExit(f"{path}: gave up after {retries} retries")


def records(payload):
    # MaintainX wraps each list under a resource key (e.g. "workOrders"); take the first list.
    return next((v for v in payload.values() if isinstance(v, list)), [])


def pull(resource, key):
    rows, cursor = [], None
    while True:
        params = {"limit": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        payload = get(resource, params, key)
        rows.extend(records(payload))
        cursor = payload.get("nextCursor")
        if not cursor:
            return rows


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        name = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, name + "."))
        elif isinstance(v, list):
            out[name] = json.dumps(v)
        else:
            out[name] = v
    return out


def write(resource, rows, outdir):
    with open(os.path.join(outdir, f"{resource}.json"), "w") as f:
        json.dump(rows, f, indent=2)
    flat = [flatten(r) for r in rows]
    cols = sorted({c for r in flat for c in r})
    with open(os.path.join(outdir, f"{resource}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(flat)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("resources", nargs="*", default=DEFAULT_RESOURCES)
    ap.add_argument("--since", help="keep records with updatedAt >= YYYY-MM-DD")
    ap.add_argument("--out", default="mx_data")
    a = ap.parse_args()
    key = os.environ.get("MAINTAINX_API_KEY")
    if not key:
        sys.exit("Set MAINTAINX_API_KEY")
    os.makedirs(a.out, exist_ok=True)
    for res in a.resources:
        rows = pull(res, key)
        if a.since:
            rows = [r for r in rows if str(r.get("updatedAt", "")) >= a.since]
        write(res, rows, a.out)
        print(f"{res}: {len(rows)} records")


if __name__ == "__main__":
    main()
