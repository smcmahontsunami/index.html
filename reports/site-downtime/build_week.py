"""Pull MaintainX site-down events for one Sunday-Saturday week (Central time).

Usage: python3 build_week.py [YYYY-MM-DD last week's Sunday] [weeks of history] [out.json]
Default last week = the most recent completed Sunday-Saturday; default history = 6 weeks.
Needs MAINTAINX_API_KEY in the environment.

Event sources, joined per site:
  * Work orders with category "Site Down" created in the week (reason text).
  * Site-asset OFFLINE status periods starting in the week (actual down/up times).
A status is matched to a work order at the same site when they overlap or start
within 60 minutes. Times come from the status when it is plausible (0 < dur < 24h),
else from the work order (created -> completed). Events still open, or longer
than 24h, are listed but excluded from hour totals and flagged for review.
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
API = "https://api.getmaintainx.com/v1"
KEY = os.environ["MAINTAINX_API_KEY"]
MATCH_WINDOW = timedelta(minutes=60)
MAX_PLAUSIBLE = timedelta(hours=24)
MERGE_GAP = timedelta(minutes=5)
OPEN_HOUR, CLOSE_HOUR = 7, 20  # only 7am-8pm Central counts toward down-time totals

CATEGORIES = [  # first match wins; equipment before staffing so "rollers ... onsite staff" is equipment
    ("Utility power", r"power is out|power outage|utilit|no power|cutting off power|power company"),
    ("IT / controls", r"connectivity|devices offline|communication|internet|network|control panel|send station"
                      r"|\bpos\b|\bapp\b|ipad|tablet|kiosk|password|controller|sonny.?s controls?"),
    ("Conveyor / chain", r"chain|sprocket|conveyor|\btrack\b|\brollers?\b|take.?up"),
    ("Hydraulic", r"hydraulic|power pack|\bhose"),
    ("Water / chemical", r"water|chemical|back ?flow"),
    ("Pit / drainage", r"\bpit\b|sump|drain"),
    ("Staffing", r"staff|associate|walk ?off|\blate\b|running late|one person|only one|1 man|nc/ns|no.?show"
                 r"|no call|did ?n.?o?t show|didn.t show|coverage|solo|call(ed|s)? ?off|new hire|opener"),
]

# Reviewer corrections (corrections.json next to this script).
_corr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corrections.json")
CORRECTIONS = json.load(open(_corr_path)) if os.path.exists(_corr_path) else {"events": {}, "added": []}


def get(path, tries=6):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + KEY})
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or 2 ** (i + 1))


def get_all(path, key, stop=None):
    out, cursor = [], None
    while True:
        sep = "&" if "?" in path else "?"
        page = get(path + (f"{sep}cursor={urllib.parse.quote(cursor)}" if cursor else ""))
        out += page[key]
        cursor = page.get("nextCursor")
        if not cursor or not page[key] or (stop and stop(page[key][-1])):
            return out


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def site_code(name):
    m = re.match(r"\s*0*(\d+)", name or "")
    return m.group(1) if m else None


def site_from_text(text, site_name):
    """Site code for a WO with no location: a leading number, else the best unique name match."""
    m = re.match(r"\s*(?:site down\s*-?\s*)?0*(\d{2,3})\b", text, re.I)
    if m and m.group(1) in site_name:
        return m.group(1)
    words = [t for t in re.findall(r"[a-z]{3,}", text.lower()) if t not in {"site", "down"}]
    scores = sorted(((sum(t in n.lower() for t in words), c) for c, n in site_name.items()), reverse=True)
    if scores and scores[0][0] >= 2 and (len(scores) == 1 or scores[0][0] > scores[1][0]):
        return scores[0][1]
    return None


def categorize(text):
    t = (text or "").lower()
    for cat, pat in CATEGORIES:
        if re.search(pat, t):
            return cat
    return "Not specified" if not t.strip() else "Other equipment"


def operating_minutes(start, end):
    """Minutes of [start, end) that fall inside 7am-8pm Central on each day."""
    start, end = start.astimezone(CT), end.astimezone(CT)
    total, day = 0.0, start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        lo = max(start, day.replace(hour=OPEN_HOUR))
        hi = min(end, day.replace(hour=CLOSE_HOUR))
        if hi > lo:
            total += (hi - lo).total_seconds() / 60
        day = (day + timedelta(days=1)).replace(hour=0)
    return round(total)


def week_bounds(start=None):
    if start:
        ws = datetime.fromisoformat(start).replace(tzinfo=CT)
    else:
        today = datetime.now(CT).replace(hour=0, minute=0, second=0, microsecond=0)
        ws = today - timedelta(days=(today.weekday() + 1) % 7 + 7)  # last completed Sunday
    return ws, ws + timedelta(days=7)


def fetch(floor):
    """Pull everything once; build() slices it per week. floor = earliest week start."""
    # Districts: team name "District N [Manager]" -> site codes via locations and assets.
    locations = {l["id"]: l["name"] for l in get_all("/locations?limit=200", "locations")}
    assets = {a["id"]: a for a in get_all("/assets?limit=200", "assets")}
    district_of, manager_of = {}, {}
    for t in get_all("/teams?limit=200", "teams"):
        m = re.match(r"\s*(District\s+\d+)\s*\[(.*?)\]", t["name"])
        if not m:
            continue
        d = get(f"/teams/{t['id']}")["team"]
        manager_of[m.group(1)] = m.group(2).replace("\xa0", " ").strip()
        names = [locations.get(i, "") for i in d.get("locationIds", [])]
        names += [assets[i]["name"] for i in d.get("assetIds", []) if i in assets]
        for n in names:
            if site_code(n):
                district_of[site_code(n)] = m.group(1)

    site_name = {}
    for name in list(locations.values()):
        c = site_code(name)
        if c and (c not in site_name or len(name) > len(site_name[c])):
            site_name[c] = name.strip()
    for code in CORRECTIONS.get("closed_sites", []):
        site_name.pop(code, None)
    for code, d in CORRECTIONS.get("districts", {}).items():  # sites not on a MaintainX district team
        district_of[code] = d
        manager_of.setdefault(d, "")
    manager_of.update(CORRECTIONS.get("managers", {}))

    # Work orders newest first; stop once older than the earliest week.
    cutoff = (floor - timedelta(days=1)).astimezone(timezone.utc).isoformat()
    wos = get_all("/workorders?limit=100&expand=categories&expand=location", "workOrders",
                  stop=lambda w: w["createdAt"] < cutoff)
    statuses = get_all("/assetstatuses?limit=200", "assetStatuses")
    return {"assets": assets, "site_name": site_name, "district_of": district_of,
            "manager_of": manager_of, "wos": wos, "statuses": statuses}


def build(ws, we, raw):
    assets, site_name, statuses = raw["assets"], raw["site_name"], raw["statuses"]
    district_of, manager_of = raw["district_of"], raw["manager_of"]
    down_wos = [w for w in raw["wos"] if "Site Down" in (w.get("categories") or [])
                and ws <= ts(w["createdAt"]) < we]

    # OFFLINE statuses on site-level assets, merged when back-to-back.
    per_site = defaultdict(list)
    for s in statuses:
        a = assets.get(s["assetId"])
        if s["status"] != "OFFLINE" or s["deletedAt"] or not a or a.get("parentId"):
            continue
        start = ts(s["startedAt"])
        if not (ws <= start < we):
            continue
        per_site[site_code(a["name"])].append(
            {"start": start, "end": ts(s["endedAt"]), "desc": (s.get("description") or "").strip(),
             "type": s.get("downtimeType")})
    merged = []
    for code, rows in per_site.items():
        rows.sort(key=lambda r: r["start"])
        for r in rows:
            last = merged[-1] if merged and merged[-1]["code"] == code else None
            if last and last["end"] and r["start"] - last["end"] <= MERGE_GAP:
                last["end"] = r["end"]
                last["desc"] = last["desc"] or r["desc"]
            else:
                merged.append({"code": code, **r})

    # OFFLINE statuses still open that began before the week ended: hygiene flags.
    stale = []
    for s in statuses:
        a = assets.get(s["assetId"])
        if (s["status"] == "OFFLINE" and not s["deletedAt"] and a and not a.get("parentId")
                and ts(s["startedAt"]) < ws and s["endedAt"] is None):
            stale.append({"site": site_name.get(site_code(a["name"]), a["name"]),
                          "since": ts(s["startedAt"]).astimezone(CT).isoformat(),
                          "note": (s.get("description") or "").strip()})

    events, used = [], set()
    for w in sorted(down_wos, key=lambda w: w["createdAt"]):
        code = site_code(w.get("location", {}).get("name") or "") or site_from_text(w["title"], site_name)
        w_start, w_end = ts(w["createdAt"]), ts(w.get("completedAt"))
        # A WO logged after the fact carries the real start in startDate (ignore date-only 00:00).
        sd = ts(w.get("startDate"))
        if sd and sd < w_start and w_start - sd < MAX_PLAUSIBLE and sd.astimezone(CT).strftime("%H:%M") != "00:00":
            w_start = sd
        match = None
        for i, s in enumerate(merged):
            if i in used or s["code"] != code:
                continue
            s_end = s["end"] or we
            overlap = s["start"] <= (w_end or we) and w_start <= s_end
            near = abs(s["start"] - w_start) <= MATCH_WINDOW or (
                w_end and abs(s["start"] - w_end) <= MATCH_WINDOW)
            if overlap or near:
                match = i
                break
        ev = {"code": code, "wo": w["sequentialId"], "wo_id": w["id"], "title": w["title"].strip(),
              "reason": (w.get("description") or "").replace("￼", "").strip()}
        if match is not None:
            used.add(match)
            s = merged[match]
            ev["reason"] = ev["reason"] or s["desc"]
            s_dur = (s["end"] - s["start"]) if s["end"] else None
            if s_dur is None or s_dur >= MAX_PLAUSIBLE:
                ev["hygiene"] = ("Offline status still open" if s_dur is None else
                                 f"Offline status left open {round(s_dur.total_seconds() / 3600)}h")
            cand = [(s["start"], s["end"], "status"), (w_start, w_end, "work order")]
        else:
            cand = [(w_start, w_end, "work order")]
        ev.update(pick_times(cand, w["status"]))
        events.append(ev)
    for i, s in enumerate(merged):  # status-only events (no Site Down WO)
        if i in used:
            continue
        ev = {"code": s["code"], "wo": None, "wo_id": None, "title": "", "reason": s["desc"]}
        ev.update(pick_times([(s["start"], s["end"], "status")], "DONE"))
        events.append(ev)

    for a in CORRECTIONS.get("added", []):  # events reported by reviewers but missing in MaintainX
        start = datetime.fromisoformat(a["start"]).replace(tzinfo=CT)
        if ws <= start < we:
            end = start + timedelta(minutes=a["minutes"])
            events.append({"code": str(a["site"]), "wo": None, "wo_id": None, "title": "Added by reviewer (not in MaintainX)",
                           "reason": a.get("reason", ""), "start": start, "end": end, "minutes": a["minutes"],
                           "time_source": "reviewer", "flag": None, "forced_category": a.get("category")})

    for ev in events:
        fix = CORRECTIONS["events"].get(f"wo:{ev['wo']}") or CORRECTIONS["events"].get(
            f"{ev['code']}@{ev['start'].astimezone(CT).strftime('%Y-%m-%dT%H:%M')}")
        if fix:
            if "minutes" in fix:
                ev.update(end=ev["start"] + timedelta(minutes=fix["minutes"]), minutes=fix["minutes"],
                          flag=None, time_source="reviewer")
                ev.pop("logged_end", None)
            if "reason" in fix:
                ev["reason"] = fix["reason"]
            if "note" in fix:
                ev["note"] = fix["note"]
            if "category" in fix:
                ev["forced_category"] = fix["category"]
            ev["corrected"] = True
        ev["site"] = site_name.get(ev["code"], ev["code"])
        ev["district"] = district_of.get(ev["code"], "Unassigned")
        ev["manager"] = manager_of.get(ev["district"], "")
        ev["category"] = ev.pop("forced_category", None) or categorize(ev["title"] + " " + ev["reason"])
        ev["overnight"] = bool(ev["end"] and ev["start"].astimezone(CT).date() != ev["end"].astimezone(CT).date())
        if ev["minutes"] is not None:  # elapsed kept for display; totals use operating hours only
            ev["elapsed_minutes"] = ev["minutes"]
            ev["minutes"] = operating_minutes(ev["start"], ev["end"])
    events.sort(key=lambda e: e["start"])
    for ev in events:
        for k in ("start", "end"):
            ev[k] = ev[k].astimezone(CT).isoformat() if ev[k] else None
        if ev.get("logged_end"):
            ev["logged_end"] = ev["logged_end"].astimezone(CT).isoformat()
    return {"week_start": ws.date().isoformat(), "week_end": (we - timedelta(days=1)).date().isoformat(),
            "events": events, "stale_offline": stale}


def pick_times(cands, wo_status):
    for start, end, src in cands:
        if end and timedelta(minutes=1) <= end - start < MAX_PLAUSIBLE:
            return {"start": start, "end": end, "minutes": round((end - start).total_seconds() / 60),
                    "time_source": src, "flag": None}
    start, end, src = cands[0]
    if wo_status != "DONE" and (not end):
        flag = "Still open - duration not final"
    elif end and end - start >= MAX_PLAUSIBLE:
        flag = f"Logged {round((end - start).total_seconds() / 3600)}h - status/WO not closed promptly; verify"
    else:
        flag = "No usable end time; verify"
    return {"start": start, "end": None, "minutes": None, "time_source": src, "flag": flag,
            "logged_end": end}


if __name__ == "__main__":
    # build_week.py [last week start Sunday YYYY-MM-DD | ""] [number of weeks] [out.json]
    last_ws, _ = week_bounds(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None)
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    starts = [last_ws - timedelta(days=7 * i) for i in reversed(range(n))]
    raw = fetch(starts[0])
    weeks = [build(ws, ws + timedelta(days=7), raw) for ws in starts]
    sites_by_district = defaultdict(list)
    for code, d in raw["district_of"].items():
        sites_by_district[d].append(code)
    out = {"generated": datetime.now(CT).isoformat(timespec="minutes"), "timezone": "America/Chicago",
           "managers": raw["manager_of"],
           "district_sites": {d: len(c) for d, c in sorted(sites_by_district.items())},
           "site_count": len(raw["site_name"]), "weeks": weeks}
    path = sys.argv[3] if len(sys.argv) > 3 else f"downtime_{weeks[-1]['week_start']}.json"
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(path, [len(w["events"]) for w in weeks], "events per week")
