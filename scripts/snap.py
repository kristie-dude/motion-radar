import json, os, time, urllib.request
URL = os.environ.get("SRC", "https://leaderboard.motion.game/api/leaderboard")
PATH = "data/history.json"
d = None
for attempt in range(3):
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "motion-radar"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        if d.get("asOf") and d.get("rows"):
            break
        print("bad payload, retrying")
    except Exception as e:
        print("fetch failed, retrying:", e)
    d = None
    time.sleep(20)
if d is None:
    raise SystemExit("could not fetch leaderboard")
os.makedirs("data", exist_ok=True)
h = json.load(open(PATH)) if os.path.exists(PATH) else {"snapshots": []}
if any(s["asOf"] == d["asOf"] for s in h["snapshots"]):
    print("already saved", d["asOf"])
    raise SystemExit(0)
rows = [[r["id"], r["name"], r["position"], r["delta"], r.get("isNew", False)] for r in d["rows"]]
h["snapshots"].append({"asOf": d["asOf"], "rows": rows})
json.dump(h, open(PATH, "w"), separators=(",", ":"))
print("saved", d["asOf"], len(rows), "creators")
